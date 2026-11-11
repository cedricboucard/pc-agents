"""
config.py — Réglages centraux du système d'agents PC.
Tout ce qui se règle (seuils, cooldowns, modèle LLM, rendu) est ici.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Optional

# ───────────── LLM local (Ollama) ─────────────
OLLAMA_URL = "http://localhost:11434"
OLLAMA_MODEL = "llama3.2:3b"      # léger et rapide ; alternatives : qwen2.5:3b, mistral:7b
LLM_TIMEOUT_S = 25
LLM_TEMPERATURE = 0.95            # haut = répliques plus vives / variées
LLM_MAX_TOKENS = 70               # force des répliques courtes

# ───────────── Télémétrie ─────────────
POLL_INTERVAL_S = 1.0             # fréquence d'échantillonnage
EMA_ALPHA = 0.4                   # lissage exponentiel de la charge (0..1, plus bas = plus lisse)

# ───────────── Anti-spam ─────────────
DIALOGUE_TURNS = 4                # nombre de répliques par échange
GLOBAL_COOLDOWN_S = 20.0          # délai minimal entre deux dialogues
EVENT_COOLDOWN_S = {              # délai minimal par (composant, type d'événement)
    "SPIKE": 45.0,
    "OVERHEAT": 60.0,
    "RECOVERY": 30.0,
}
QUEUE_MAX = 3                     # événements en attente max ; au-delà, on jette

# ───────────── Rendu CLI ─────────────
TYPEWRITER_DELAY_S = 0.012        # effet « machine à écrire » (0 pour désactiver)
WRAP_WIDTH = 78


@dataclass(frozen=True)
class Thresholds:
    """Seuils d'un composant. L'écart spike/idle crée l'hystérésis (évite le clignotement)."""
    spike: float                  # charge lissée (%) au-dessus de laquelle on parle de « pic »
    idle: float                   # charge lissée (%) en dessous de laquelle on parle de « repos »
    spike_samples: int            # nb d'échantillons consécutifs au-dessus de `spike`
    recover_samples: int          # nb d'échantillons consécutifs au repos avant « retour au calme »
    temp_hot: Optional[float]     # °C déclenchant OVERHEAT (None = pas de capteur / non applicable)
    temp_recover: Optional[float] # °C sous lesquels on considère que ça a refroidi


THRESHOLDS = {
    "CPU": Thresholds(spike=85, idle=30, spike_samples=3, recover_samples=5, temp_hot=85, temp_recover=70),
    "GPU": Thresholds(spike=90, idle=15, spike_samples=3, recover_samples=5, temp_hot=82, temp_recover=65),
    "RAM": Thresholds(spike=88, idle=70, spike_samples=3, recover_samples=8, temp_hot=None, temp_recover=None),
}

# ───────────── Chat interactif ─────────────
HISTORY_SIZE = 10                 # nb de répliques gardées en mémoire (les agents « se souviennent »)
