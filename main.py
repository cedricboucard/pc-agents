#!/usr/bin/env python3
"""
main.py — Point d'entrée.

Threads :
  [main]    boucle de télémétrie → EventEngine → file de jobs
  [worker]  consomme la file (événements ET messages de l'humain) → LLM → Renderer
  [input]   lit le clavier (chat interactif)
Le LLM étant lent, la télémétrie n'est JAMAIS bloquée par la génération.

Usage :
  python main.py                 # télémétrie réelle + Ollama + chat
  python main.py --demo          # scénario simulé
  python main.py --no-llm        # répliques de secours uniquement
  python main.py --no-chat       # sans saisie clavier (surveillance seule)
"""
from __future__ import annotations
import argparse
import queue
import re
import threading

import config
from llm import DialogueGenerator, OllamaClient
from renderer import Renderer
from telemetry import DemoTelemetry, RealTelemetry
from triggers import EventEngine

MENTION = re.compile(r"^@(cpu|gpu|ram)\b[:,]?\s*(.*)$", re.I | re.S)
HELP = ("Écris un message pour parler aux trois composants.\n"
        "  @cpu <msg> | @gpu <msg> | @ram <msg>   interpeller un composant en particulier\n"
        "  /status   métriques actuelles   /help   cette aide   /quit   quitter")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Les composants du PC se parlent (et te parlent).")
    p.add_argument("--demo", action="store_true", help="télémétrie simulée")
    p.add_argument("--no-llm", action="store_true", help="n'utilise pas Ollama")
    p.add_argument("--no-chat", action="store_true", help="désactive la saisie clavier")
    p.add_argument("--model", default=config.OLLAMA_MODEL)
    p.add_argument("--url", default=config.OLLAMA_URL)
    p.add_argument("--interval", type=float, default=config.POLL_INTERVAL_S)
    p.add_argument("--turns", type=int, default=config.DIALOGUE_TURNS)
    p.add_argument("--no-typewriter", action="store_true")
    return p.parse_args()


def input_loop(jobs, components, snapshot, renderer, stop) -> None:
    """Lit le clavier et transforme chaque ligne en commande ou en job « chat »."""
    while not stop.is_set():
        try:
            raw = input()
        except EOFError:
            return                                   # stdin fermé (pipe) : on laisse tourner le reste
        text = raw.strip()
        if not text:
            renderer.prompt()
        elif text in ("/quit", "/exit", "/q"):
            stop.set()
            return
        elif text == "/help":
            renderer.info(HELP)
            renderer.prompt()
        elif text == "/status":
            for name, s in dict(snapshot).items():
                renderer.info(f"  {name:<4} {s.short()}")
            renderer.prompt()
        else:
            target = None
            m = MENTION.match(text)
            if m:
                target, text = m.group(1).upper(), (m.group(2).strip() or "Ça va ?")
                if target not in components:
                    renderer.info(f"{target} n'est pas présent sur cette machine.")
                    renderer.prompt()
                    continue
            jobs.put(("chat", text, target))


def main() -> None:
    args = parse_args()
    config.DIALOGUE_TURNS = args.turns

    telemetry = DemoTelemetry() if args.demo else RealTelemetry()
    renderer = Renderer(typewriter=not args.no_typewriter)
    renderer.intro(telemetry.components)

    client = None
    if not args.no_llm:
        c = OllamaClient(args.url, args.model)
        if c.is_up():
            client = c
            renderer.info(f"LLM : Ollama / {args.model}")
        else:
            renderer.info("Ollama injoignable → répliques de secours (vérifie `systemctl status ollama`).")
    generator = DialogueGenerator(client, telemetry.components)

    jobs: "queue.Queue" = queue.Queue()               # événements + messages de l'humain
    snapshot: dict = {}                               # dernier état connu
    stop = threading.Event()

    def worker() -> None:
        while not stop.is_set():
            try:
                job = jobs.get(timeout=0.5)
            except queue.Empty:
                continue
            if job[0] == "event":
                renderer.banner(job[1])
                generator.run(job[1], dict(snapshot), renderer.say)
            else:                                     # ("chat", texte, cible)
                generator.user_turn(job[1], job[2], dict(snapshot), renderer.say)
            if not args.no_chat:
                renderer.prompt()

    threading.Thread(target=worker, daemon=True).start()

    if not args.no_chat:
        threading.Thread(target=input_loop, daemon=True,
                         args=(jobs, telemetry.components, snapshot, renderer, stop)).start()
        renderer.info("Surveillance en cours. Parle-leur : message libre, @cpu / @gpu / @ram, /help. Ctrl+C pour quitter.")
        renderer.prompt()
    else:
        renderer.info("Surveillance en cours — Ctrl+C pour quitter.\n")

    engine = EventEngine()
    try:
        while not stop.is_set():
            samples = telemetry.read_all()
            snapshot.clear()
            snapshot.update(samples)
            ev = engine.update(samples)
            if ev is not None and jobs.qsize() < config.QUEUE_MAX:   # trop d'attente : on jette
                jobs.put(("event", ev))
            stop.wait(args.interval)
    except KeyboardInterrupt:
        pass
    stop.set()
    renderer.info("\nLes composants se taisent. À bientôt.")


if __name__ == "__main__":
    main()
