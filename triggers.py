"""
triggers.py — Détection d'événements critiques SANS spam.

Techniques anti-spam :
  1. Lissage EMA de la charge (un pic d'1 s ne compte pas).
  2. Confirmation sur N échantillons consécutifs.
  3. Hystérésis : seuil haut (spike) ≠ seuil bas (idle), plus un seuil de refroidissement.
  4. Machine à états par composant : on ne répète pas SPIKE tant qu'on n'est pas revenu au calme.
  5. Cooldown par (composant, type) + cooldown global entre dialogues (OVERHEAT le contourne).
  6. « Retour au repos » annoncé uniquement si un pic/surchauffe avait été annoncé.
"""
from __future__ import annotations
import time
from dataclasses import dataclass
from typing import Dict, List, Optional

import config
from telemetry import Sample

_PRIORITY = {"OVERHEAT": 0, "SPIKE": 1, "RECOVERY": 2}


@dataclass
class Event:
    component: str
    kind: str            # SPIKE | OVERHEAT | RECOVERY
    sample: Sample
    ts: float


class _Tracker:
    """Machine à états d'un composant : calm → stressed → hot → calm."""

    def __init__(self, th: config.Thresholds) -> None:
        self.th = th
        self.ema: Optional[float] = None
        self.hi = 0
        self.lo = 0
        self.state = "calm"
        self.announced = False       # un SPIKE/OVERHEAT a-t-il été réellement émis ?

    def update(self, s: Sample) -> Optional[str]:
        th = self.th
        a = config.EMA_ALPHA
        self.ema = s.load if self.ema is None else a * s.load + (1 - a) * self.ema

        is_hot = th.temp_hot is not None and s.temp is not None and s.temp >= th.temp_hot
        is_cool = th.temp_recover is None or s.temp is None or s.temp <= th.temp_recover

        self.hi = self.hi + 1 if self.ema >= th.spike else 0
        self.lo = self.lo + 1 if (self.ema <= th.idle and is_cool) else 0

        if is_hot and self.state != "hot":
            self.state = "hot"
            return "OVERHEAT"
        if self.state == "calm" and self.hi >= th.spike_samples:
            self.state = "stressed"
            return "SPIKE"
        if self.state != "calm" and self.lo >= th.recover_samples:
            self.state = "calm"
            return "RECOVERY"
        return None


class EventEngine:
    def __init__(self) -> None:
        self._trackers: Dict[str, _Tracker] = {}
        self._last_event: Dict[tuple, float] = {}
        self._last_global = 0.0

    def update(self, samples: Dict[str, Sample]) -> Optional[Event]:
        """Traite un tick de télémétrie ; renvoie AU PLUS un événement (le plus prioritaire)."""
        now = time.time()
        candidates: List[Event] = []
        for name, s in samples.items():
            th = config.THRESHOLDS.get(name)
            if th is None:
                continue
            tracker = self._trackers.setdefault(name, _Tracker(th))
            kind = tracker.update(s)
            if kind is None:
                continue
            if kind == "RECOVERY":
                if not tracker.announced:
                    continue
                tracker.announced = False
            candidates.append(Event(name, kind, s, now))

        if not candidates:
            return None
        ev = min(candidates, key=lambda e: _PRIORITY[e.kind])

        # Cooldowns
        if now - self._last_event.get((ev.component, ev.kind), 0) < config.EVENT_COOLDOWN_S[ev.kind]:
            return None
        if ev.kind != "OVERHEAT" and now - self._last_global < config.GLOBAL_COOLDOWN_S:
            return None

        if ev.kind in ("SPIKE", "OVERHEAT"):
            self._trackers[ev.component].announced = True
        self._last_event[(ev.component, ev.kind)] = now
        self._last_global = now
        return ev
