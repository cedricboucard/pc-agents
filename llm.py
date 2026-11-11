"""
llm.py — Client Ollama + orchestrateur de dialogue multi-agents.

Principe : chaque réplique = un appel LLM distinct avec le system prompt de L'AGENT qui parle
et la mémoire de conversation partagée (événements, répliques, messages de l'humain).
Deux déclencheurs :
  - run()       : un événement matériel (pic, surchauffe, repos)
  - user_turn() : l'humain écrit dans le terminal (à tous, ou à un agent via @cpu / @gpu / @ram)
Si Ollama est indisponible, on bascule sur les répliques de secours (le système ne plante jamais).
"""
from __future__ import annotations
import random
import re
from collections import deque
from typing import Callable, Deque, Dict, List, Optional

import requests

import config
from personalities import AGENTS, EVENT_TEXT
from telemetry import Sample
from triggers import Event


class OllamaClient:
    def __init__(self, url: str, model: str) -> None:
        self.url = url.rstrip("/")
        self.model = model

    def is_up(self) -> bool:
        try:
            return requests.get(f"{self.url}/api/tags", timeout=2).ok
        except requests.RequestException:
            return False

    def chat(self, system: str, user: str) -> str:
        payload = {
            "model": self.model,
            "stream": False,
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": user}],
            "options": {"temperature": config.LLM_TEMPERATURE,
                        "num_predict": config.LLM_MAX_TOKENS},
        }
        r = requests.post(f"{self.url}/api/chat", json=payload, timeout=config.LLM_TIMEOUT_S)
        r.raise_for_status()
        return r.json()["message"]["content"]


def _clean(text: str, speaker: str) -> str:
    """Nettoie une sortie de LLM : préfixe de nom, guillemets, didascalies, longueur."""
    text = text.strip().splitlines()[0] if text.strip() else ""
    text = re.sub(rf"^\s*{speaker}\s*[:\-—]\s*", "", text, flags=re.I)
    text = re.sub(r"\*[^*]*\*", "", text)          # didascalies *soupire*
    text = text.strip(" \"'«»")
    return text[:220]


class DialogueGenerator:
    def __init__(self, client: Optional[OllamaClient], active: List[str]) -> None:
        self.client = client
        self.active = active                                   # composants réellement présents
        self.history: Deque[str] = deque(maxlen=config.HISTORY_SIZE)  # mémoire partagée

    # ───────────── brique de base : une réplique ─────────────
    def _line(self, speaker: str, situation: str, kind: str,
              snapshot: Dict[str, Sample]) -> str:
        agent = AGENTS[speaker]
        if self.client is not None:
            state = " | ".join(f"{k}: {v.short()}" for k, v in snapshot.items())
            history = "\n".join(self.history) if self.history else "(rien pour l'instant)"
            user = (f"SITUATION : {situation}\nÉTAT DU PC : {state}\n"
                    f"CONVERSATION JUSQU'ICI :\n{history}\n\n"
                    f"À toi, {speaker}. Une seule réplique courte :")
            try:
                line = _clean(self.client.chat(agent.system_prompt, user), speaker)
                if line:
                    return line
            except Exception:
                self.client = None                             # LLM tombé : secours définitif
        pool = agent.fallback.get(kind) or ["..."]
        return random.choice(pool)

    def _converse(self, speakers: List[str], situation_for: Callable[[str], str], kind: str,
                  snapshot: Dict[str, Sample], say: Callable[[str, str], None]) -> None:
        for speaker in speakers:
            line = self._line(speaker, situation_for(speaker), kind, snapshot)
            self.history.append(f"{speaker}: {line}")
            say(speaker, line)

    # ───────────── déclencheur 1 : événement matériel ─────────────
    def run(self, event: Event, snapshot: Dict[str, Sample],
            say: Callable[[str, str], None]) -> None:
        situation = EVENT_TEXT[event.kind].format(c=event.component, m=event.sample.short())
        self.history.append(f"[événement] {situation}")
        order = [event.component] + [c for c in self.active if c != event.component]
        speakers = [order[i % len(order)] for i in range(config.DIALOGUE_TURNS)]
        self._converse(speakers, lambda _s: situation, event.kind, snapshot, say)

    # ───────────── déclencheur 2 : l'humain parle ─────────────
    def user_turn(self, text: str, target: Optional[str], snapshot: Dict[str, Sample],
                  say: Callable[[str, str], None]) -> None:
        """target = 'CPU' | 'GPU' | 'RAM' si interpellé directement, None = message à tous."""
        self.history.append(f"HUMAIN: {text}")
        if target in self.active:
            others = [c for c in self.active if c != target]
            speakers = [target] + random.sample(others, 1 if others else 0)  # +1 réaction d'un collègue
        else:
            speakers = random.sample(self.active, len(self.active))          # tout le monde répond

        def situation_for(speaker: str) -> str:
            if target is None:
                return (f"L'humain, propriétaire du PC, s'adresse à vous trois : « {text} ». "
                        "Réponds-lui directement, et réagis aux répliques de tes collègues.")
            if speaker == target:
                return f"L'humain, propriétaire du PC, t'interpelle directement : « {text} ». Réponds-lui."
            return (f"L'humain a dit à {target} : « {text} ». "
                    f"Tu écoutais : réagis à sa question ou à la réponse de {target}.")

        self._converse(speakers, situation_for, "CHAT", snapshot, say)
