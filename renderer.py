"""
renderer.py — Affichage terminal : couleurs ANSI par composant, effet machine à écrire,
sortie thread-safe (le thread de dialogue et le thread principal ne se mélangent pas).
"""
from __future__ import annotations
import os
import sys
import textwrap
import threading
import time

import config
from personalities import AGENTS
from triggers import Event

RESET, BOLD, DIM = "\033[0m", "\033[1m", "\033[2m"
RED, GREEN, YELLOW = "\033[91m", "\033[92m", "\033[93m"

_KIND_STYLE = {
    "SPIKE": (YELLOW, "PIC DE CHARGE"),
    "OVERHEAT": (RED, "SURCHAUFFE"),
    "RECOVERY": (GREEN, "RETOUR AU REPOS"),
}


class Renderer:
    def __init__(self, typewriter: bool = True) -> None:
        self._lock = threading.Lock()
        self._delay = config.TYPEWRITER_DELAY_S if typewriter else 0.0
        if os.name == "nt":                           # active l'interprétation ANSI sous Windows
            os.system("")
            try:
                import colorama
                colorama.just_fix_windows_console()
            except ImportError:
                pass

    def _write(self, text: str, slow: bool = False) -> None:
        if slow and self._delay > 0:
            for ch in text:
                sys.stdout.write(ch)
                sys.stdout.flush()
                time.sleep(self._delay)
        else:
            sys.stdout.write(text)
            sys.stdout.flush()

    def info(self, text: str) -> None:
        with self._lock:
            self._write(f"{DIM}{text}{RESET}\n")

    def prompt(self) -> None:
        """Réaffiche l'invite de saisie (après chaque dialogue)."""
        with self._lock:
            self._write(f"\n{GREEN}{BOLD}Toi ▸ {RESET}")

    def intro(self, components) -> None:
        with self._lock:
            self._write(f"{BOLD}=== Le PC a des choses à dire ==={RESET}\n")
            for name in components:
                a = AGENTS[name]
                self._write(f"  {a.color}{BOLD}{name:<4}{RESET} {DIM}{a.role}{RESET}\n")
            self._write("\n")

    def banner(self, ev: Event) -> None:
        color, label = _KIND_STYLE[ev.kind]
        with self._lock:
            self._write(f"\r\033[K\n{color}{BOLD}── {label} · {ev.component} · {ev.sample.short()} ──{RESET}\n")

    def say(self, speaker: str, text: str) -> None:
        agent = AGENTS[speaker]
        stamp = time.strftime("%H:%M:%S")
        prefix = f"{DIM}{stamp}{RESET} {agent.color}{BOLD}{speaker:<4}{RESET} {agent.color}│{RESET} "
        indent = " " * 15 + f"{agent.color}│{RESET} "
        lines = textwrap.wrap(text, width=config.WRAP_WIDTH) or [""]
        with self._lock:
            for i, line in enumerate(lines):
                self._write(("\r\033[K" + prefix) if i == 0 else indent)
                self._write(f"{agent.color}{line}{RESET}\n", slow=True)
