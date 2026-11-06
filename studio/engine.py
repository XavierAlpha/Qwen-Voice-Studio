"""Lazy Qwen inference adapter. No dependency upgrades, downloads or FP16 fallback."""
from collections import OrderedDict
from contextlib import contextmanager
from pathlib import Path
import gc
import sys
import threading
import time
import numpy as np
from .schema import Generate, Runtime

class Cancelled(Exception):
    pass


class InferencePhaseError(RuntimeError):
    """Carries a non-sensitive phase tag while preserving the real exception.

    Never render the original exception text: upstream exceptions can include
    transcripts, paths or environment-specific identifying information.
    """

    def __init__(self, phase: str, cause: Exception):
        super().__init__(phase)
        self.phase = phase
        self.original = cause


@contextmanager
def cancellable_talker(wrapper, cancel):
    """Inject at the actual HF generation call; top-level kwargs may be dropped.

    Instance-scoped and protected by the engine lock. Never modifies site-packages.
    Model loading and GPU kernels remain cooperative, not forcibly preemptible.
    """
    talker = getattr(getattr(wrapper, "model", None), "talker", None)
    if talker is None or not callable(getattr(talker, "generate", None)):
        yield
        return
    from transformers import StoppingCriteria, StoppingCriteriaList

    class StopOnCancel(StoppingCriteria):
        def __call__(self, input_ids, scores, **kwargs):
            if cancel.is_set():
                raise Cancelled()
            return False

    had_local = "generate" in talker.__dict__
    original_local = talker.__dict__.get("generate")
    original = talker.generate

    def generate(*args, **kwargs):
        if cancel.is_set():
            raise Cancelled()
        criteria = list(kwargs.pop("stopping_criteria", None) or [])
        kwargs["stopping_criteria"] = StoppingCriteriaList([*criteria, StopOnCancel()])
        return original(*args, **kwargs)

    talker.generate = generate
    try:
        yield
    finally:
        if had_local:
            talker.generate = original_local
        else:
            delattr(talker, "generate")


class QwenEngine:
    def __init__(self, root: Path, config=None):
        self.root = root
        self.config = config
        self._hardware_cache = None
        self._hardware_at = 0
        self.model = None
        self.key = None
        self.info = {"loaded": False}
        self.lock = threading.RLock()
        self.clone_cache = OrderedDict()

    def hardware(self):
        if self._hardware_cache is not None and time.monotonic() - self._hardware_at < 3:
            return {**self._hardware_cache, "model": self.info.copy()}
        import torch
        import psutil
        available = torch.cuda.is_available()
        from .inference_runtime import mixed_device_available
        result = {"cuda": available, "gpu": torch.cuda.get_device_name(0) if available else None,
                "vram_gib": round(torch.cuda.get_device_properties(0).total_memory / 1024**3, 2) if available else 0,
                "ram_free_gib": round(psutil.virtual_memory().available / 1024**3, 1),
                "torch": torch.__version__, "cuda_version": torch.version.cuda,
                "bf16": bool(available and torch.cuda.get_device_capability(0)[0] >= 8 and torch.cuda.is_bf16_supported()),
                "hybrid_ready": bool(available and mixed_device_available()), "model": self.info.copy()}
        self._hardware_cache, self._hardware_at = result, time.monotonic()
        return result

    def resolve_runtime(self, record, runtime):
        import torch
        if runtime.device != "auto":
            return runtime, "explicit"
        if not torch.cuda.is_available():
            return runtime.model_copy(update={"device": "cpu"}), "CUDA unavailable; CPU FP32"
        # Auto mode only selects an available compute backend/precision. It must
        # not estimate VRAM, override user budgets, or silently move work to CPU.
        native_bf16 = torch.cuda.get_device_capability(0)[0] >= 8 and torch.cuda.is_bf16_supported()
        choice = "cuda_bf16" if native_bf16 else "cuda_fp32"
        return runtime.model_copy(update={"device": choice}), "CUDA capability detected; no memory estimate"

    def unload(self):
        with self.lock:
            if self.model and hasattr(self.model, "release_fast_generation"):
                self.model.release_fast_generation()
            self.model, self.key = None, None
            self.clone_cache.clear()
            self.info = {"loaded": False}
            gc.collect()
            torch = sys.modules.get("torch")
            if torch is not None and torch.cuda.is_available():
                torch.cuda.empty_cache()

    def load(self, record: dict, runtime: Runtime) -> dict:
        import torch
        requested = runtime.model_dump()
        with self.lock:
            # Reuse a matching already-loaded model instead of reloading it.
            if (self.model is not None and self.key is not None
                    and self.key[:2] == (record["id"], record.get("fingerprint"))
                    and self.info.get("requested_runtime") == requested):
                return self.info.copy()
            self.unload()
            runtime, reason = self.resolve_runtime(record, runtime)
            key = (record["id"], record.get("fingerprint"), runtime.model_dump_json())
            if runtime.device != "cpu" and not torch.cuda.is_available():
                raise ValueError("CUDA unavailable. Select CPU FP32 or install the appropriate CUDA PyTorch build.")
            if runtime.device == "cuda_bf16" and not (torch.cuda.get_device_capability(0)[0] >= 8 and torch.cuda.is_bf16_supported()):
                raise ValueError("This GPU does not support BF16. Use FP32.")
            from .inference_runtime import install_mixed_device_support, mixed_device_available
            if runtime.device == "hybrid" and not mixed_device_available():
                raise ValueError("Hybrid execution requires qwen-tts and accelerate. Install the project inference dependencies.")
            # Internal adaptations are part of this project, not a separately
            # checked-out WebUI. Import lazily to keep the HTTP server light.
            install_mixed_device_support()
            from qwen_tts import Qwen3TTSModel
            model_class = Qwen3TTSModel
            kwargs = {"local_files_only": True, "attn_implementation": runtime.attention, "dtype": torch.float32, "trust_remote_code": False, "use_safetensors": True}
            if runtime.device == "hybrid":
                # Honor explicit per-device budgets as provided. Let accelerate
                # and PyTorch report actual allocation errors rather than guessing.
                kwargs.update(device_map="auto", max_memory={0: int(runtime.gpu_gib * 1024**3),
                                                              "cpu": int(runtime.cpu_gib * 1024**3)},
                              low_cpu_mem_usage=True)
            else:
                kwargs["device_map"] = "cpu" if runtime.device == "cpu" else "cuda:0"
                if runtime.device == "cuda_fp16":
                    kwargs["dtype"] = torch.float16
                elif runtime.device == "cuda_bf16":
                    kwargs["dtype"] = torch.bfloat16
            started = time.perf_counter()
            try:
                model = model_class.from_pretrained(record["path"], **kwargs)
                expected = {"design": "voice_design", "clone": "base", "custom": "custom_voice"}[record["mode"]]
                if getattr(model.model, "tts_model_type", None) != expected:
                    raise ValueError("Checkpoint task differs from its registered configuration")
                from .device_utils import execution_device
                compute_device = str(execution_device(model.model))
                placement = {k: str(v) for k, v in (getattr(model.model, "hf_device_map", {}) or {}).items()}
                self.info = {"loaded": True, "model_id": record["id"], "name": record["name"], "mode": record["mode"],
                             "placement": placement, "execution_device": compute_device, "runtime": runtime.model_dump(), "load_seconds": round(time.perf_counter()-started, 2),
                             "backend": "integrated", "speakers": model.get_supported_speakers() or [],
                             "selection_reason": reason, "requested_runtime": requested}
                self.model, self.key = model, key
                return self.info.copy()
            except Exception:
                self.unload()
                raise

    def generate(self, request: Generate, text: str, reference: Path | None, cancel: threading.Event):
        import torch
        from transformers import set_seed
        if cancel.is_set():
            raise Cancelled()
        with self.lock:
            if self.model is None:
                raise RuntimeError("No model loaded")
            if request.sampling.seed >= 0:
                set_seed(request.sampling.seed)
            kwargs = request.sampling.model_dump(exclude={"seed"})
            kwargs.update(text=text, language=request.language, do_sample=True, non_streaming_mode=True)
            with torch.inference_mode(), cancellable_talker(self.model, cancel):
                if request.mode == "design":
                    try:
                        result = self.model.generate_voice_design(instruct=request.instruct, **kwargs)
                    except Cancelled:
                        raise
                    except Exception as error:
                        raise InferencePhaseError("speech_generation", error) from error
                elif request.mode == "custom":
                    try:
                        result = self.model.generate_custom_voice(speaker=request.speaker, instruct=request.instruct, **kwargs)
                    except Cancelled:
                        raise
                    except Exception as error:
                        raise InferencePhaseError("speech_generation", error) from error
                else:
                    if reference is None:
                        raise ValueError("Reference audio missing")
                    cache_key = (str(reference), request.ref_text, request.x_vector_only)
                    prompt = self.clone_cache.get(cache_key)
                    if prompt is None:
                        try:
                            # Explicitly decode the locally validated WAV into the
                            # tuple supported by Qwen. Avoid backend-specific URL/
                            # path loaders and make the reference boundary observable.
                            import soundfile as sf
                            audio, rate = sf.read(str(reference), dtype="float32", always_2d=False)
                            if getattr(audio, "ndim", 1) != 1:
                                audio = audio.mean(axis=1)
                            prompt = self.model.create_voice_clone_prompt(
                                ref_audio=(audio, int(rate)),
                                ref_text=request.ref_text or None,
                                x_vector_only_mode=request.x_vector_only,
                            )
                        except Cancelled:
                            raise
                        except Exception as error:
                            raise InferencePhaseError("reference_encoding", error) from error
                        self.clone_cache[cache_key] = prompt
                        while len(self.clone_cache) > 3:
                            self.clone_cache.popitem(last=False)
                    self.clone_cache.move_to_end(cache_key)
                    try:
                        result = self.model.generate_voice_clone(voice_clone_prompt=prompt, **kwargs)
                    except Cancelled:
                        raise
                    except Exception as error:
                        raise InferencePhaseError("speech_generation", error) from error
            if cancel.is_set():
                raise Cancelled()
            return result[0][0], int(result[1])

    def reset_metrics(self):
        import torch
        if torch.cuda.is_available():
            torch.cuda.synchronize()
            torch.cuda.reset_peak_memory_stats()

    def metrics(self):
        import torch
        if not torch.cuda.is_available():
            return {"vram_gib": 0}
        torch.cuda.synchronize()
        return {"vram_gib": round(torch.cuda.max_memory_allocated()/1024**3, 3)}
