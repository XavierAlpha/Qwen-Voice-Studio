"""Test-only audio engine. Never used for real model performance claims."""
import time
import numpy as np
from studio.engine import Cancelled


class DemoEngine:
    """Explicit test-harness injection only. Test tone, NEVER a synthetic speech benchmark."""
    def __init__(self):
        self.info = {"loaded": False}
    def hardware(self):
        return {"cuda": False, "gpu": None, "vram_gib": 0, "ram_free_gib": 0, "torch": "demo", "cuda_version": None, "bf16": False, "patched_backend": False, "model": self.info.copy()}
    def load(self, record, runtime):
        time.sleep(0.04)
        self.info = {"loaded": True, "model_id": record["id"], "name": record["name"], "mode": record["mode"], "backend": "test-tone", "placement": {}, "speakers": record.get("speakers", [])}
        return self.info.copy()
    def unload(self):
        self.info = {"loaded": False}
    def reset_metrics(self):
        pass
    def metrics(self):
        return {"vram_gib": 0}
    def generate(self, request, text, reference, cancel):
        for _ in range(10):
            if cancel.is_set():
                raise Cancelled()
            time.sleep(0.025)
        sr = 24000
        t = np.arange(int(sr * min(3, max(.7, len(text) / 15)))) / sr
        envelope = np.sin(np.pi*np.arange(len(t))/len(t))**2
        wave = .15 * np.sin(2*np.pi*220*t) * envelope
        return wave.astype(np.float32), sr
