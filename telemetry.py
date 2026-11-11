"""
telemetry.py — Collecte des métriques matérielles.

- CPU / RAM : psutil (multi-plateforme). La température CPU n'est exposée que sous Linux/macOS ;
  sous Windows elle vaudra None (les agents s'en accommodent).
- GPU : pynvml (NVIDIA uniquement). Si absent, l'agent GPU est simplement désactivé.
- DemoTelemetry : scénario simulé pour tester sans stresser la machine.
"""
from __future__ import annotations
import math
import random
import time
from dataclasses import dataclass
from typing import Dict, Optional

import psutil


@dataclass
class Sample:
    """Instantané des métriques d'un composant."""
    component: str
    load: float                          # charge en %
    temp: Optional[float] = None         # °C
    freq_mhz: Optional[float] = None     # MHz
    detail: str = ""                     # info libre (ex. swap, VRAM)

    def short(self) -> str:
        """Résumé lisible, injecté dans les prompts du LLM."""
        parts = [f"charge {self.load:.0f}%"]
        if self.temp is not None:
            parts.append(f"{self.temp:.0f}°C")
        if self.freq_mhz:
            parts.append(f"{self.freq_mhz / 1000:.1f} GHz")
        if self.detail:
            parts.append(self.detail)
        return ", ".join(parts)


# ───────────────────────── Collecteurs réels ─────────────────────────

class CpuCollector:
    name = "CPU"
    _SENSOR_KEYS = ("coretemp", "k10temp", "zenpower", "cpu_thermal", "cpu-thermal", "acpitz")

    def __init__(self) -> None:
        psutil.cpu_percent(interval=None)  # amorçage : le 1er appel renvoie toujours 0

    def _temperature(self) -> Optional[float]:
        if not hasattr(psutil, "sensors_temperatures"):
            return None                    # Windows
        try:
            sensors = psutil.sensors_temperatures()
        except Exception:
            return None
        for key in self._SENSOR_KEYS:
            if key in sensors and sensors[key]:
                return float(sensors[key][0].current)
        return None

    def read(self) -> Sample:
        freq = psutil.cpu_freq()
        return Sample("CPU", psutil.cpu_percent(interval=None),
                      self._temperature(), freq.current if freq else None)


class GpuCollector:
    name = "GPU"

    def __init__(self) -> None:
        self._nvml = None
        self._handle = None
        try:
            import pynvml
            pynvml.nvmlInit()
            self._handle = pynvml.nvmlDeviceGetHandleByIndex(0)
            self._nvml = pynvml
        except Exception:
            pass                           # pas de GPU NVIDIA / pilote absent

    @property
    def available(self) -> bool:
        return self._nvml is not None

    def read(self) -> Sample:
        n, h = self._nvml, self._handle
        util = n.nvmlDeviceGetUtilizationRates(h).gpu
        temp = n.nvmlDeviceGetTemperature(h, n.NVML_TEMPERATURE_GPU)
        clock = n.nvmlDeviceGetClockInfo(h, n.NVML_CLOCK_GRAPHICS)
        mem = n.nvmlDeviceGetMemoryInfo(h)
        return Sample("GPU", float(util), float(temp), float(clock),
                      f"VRAM {mem.used / mem.total * 100:.0f}%")


class RamCollector:
    name = "RAM"

    def read(self) -> Sample:
        vm, sw = psutil.virtual_memory(), psutil.swap_memory()
        detail = f"{vm.used / 2**30:.1f}/{vm.total / 2**30:.0f} Go, swap {sw.percent:.0f}%"
        return Sample("RAM", vm.percent, None, None, detail)


class RealTelemetry:
    """Agrège les collecteurs disponibles."""

    def __init__(self) -> None:
        self._collectors = [CpuCollector(), RamCollector()]
        gpu = GpuCollector()
        if gpu.available:
            self._collectors.insert(1, gpu)          # ordre : CPU, GPU, RAM

    @property
    def components(self):
        return [c.name for c in self._collectors]

    def read_all(self) -> Dict[str, Sample]:
        out = {}
        for c in self._collectors:
            try:
                out[c.name] = c.read()
            except Exception:
                pass                                  # un capteur capricieux ne doit pas tout casser
        return out


# ───────────────────────── Mode démo ─────────────────────────

class DemoTelemetry:
    """Cycle de 70 s : calme → pic → surchauffe → retour au calme. Pour tester sans risque."""
    components = ["CPU", "GPU", "RAM"]

    def __init__(self) -> None:
        self._t0 = time.time()

    def read_all(self) -> Dict[str, Sample]:
        t = (time.time() - self._t0) % 70
        j = lambda a: random.uniform(-a, a)
        if t < 12:      cpu, gpu, ram, ct, gt = 18, 8, 52, 48, 42
        elif t < 30:    cpu, gpu, ram, ct, gt = 96, 98, 90, 78, 76
        elif t < 45:    cpu, gpu, ram, ct, gt = 93, 95, 92, 89, 86
        else:           cpu, gpu, ram, ct, gt = 14, 6, 55, 50, 44
        return {
            "CPU": Sample("CPU", cpu + j(3), ct + j(1), 4200 + j(100)),
            "GPU": Sample("GPU", gpu + j(2), gt + j(1), 1900 + j(50), "VRAM 71%"),
            "RAM": Sample("RAM", ram + j(1), None, None, f"{ram / 100 * 16:.1f}/16 Go, swap {max(0, ram - 80):.0f}%"),
        }
