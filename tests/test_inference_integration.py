"""Contracts for in-tree Qwen low-VRAM corrections and clone diagnostics.

These tests deliberately use stand-in Qwen classes; a real GPU/model inference
must be verified separately on the target Windows machine.
"""
from contextlib import nullcontext
from pathlib import Path
from types import ModuleType, SimpleNamespace
import sys
import threading

import numpy as np
import pytest


def test_mixed_device_patch_uses_actual_execution_hook(monkeypatch):
    torch = pytest.importorskip("torch")
    import studio.inference_runtime as runtime
    monkeypatch.setattr(runtime, "_PATCHED", False)

    class Base:
        _no_split_modules = []
        def __init__(self):
            self._hf_hook = SimpleNamespace(execution_device=torch.device("cuda:0"))
        def parameters(self):
            yield torch.empty(1, device="meta")
        def buffers(self):
            return iter(())
        def modules(self):
            return iter((self,))

    class Talker(Base):
        _no_split_modules = []

    class Tokenizer:
        last_kwargs = None
        @classmethod
        def from_pretrained(cls, path, **kwargs):
            cls.last_kwargs = kwargs
            return SimpleNamespace(model=Base(), device=torch.device("meta"))

    class Wrapper:
        def __init__(self, model, processor, generate_defaults=None):
            self.model = model
            self.processor = processor
            self.generate_defaults = generate_defaults
            self.device = model.device

    model_module = ModuleType("qwen_tts.core.models.modeling_qwen3_tts")
    model_module.Qwen3TTSPreTrainedModel = Base
    model_module.Qwen3TTSTalkerTextPreTrainedModel = Talker
    core_models = ModuleType("qwen_tts.core.models")
    core_models.modeling_qwen3_tts = model_module
    tokenizer_module = ModuleType("qwen_tts.inference.qwen3_tts_tokenizer")
    tokenizer_module.Qwen3TTSTokenizer = Tokenizer
    wrapper_module = ModuleType("qwen_tts.inference.qwen3_tts_model")
    wrapper_module.Qwen3TTSModel = Wrapper
    for key, value in {
        "qwen_tts": ModuleType("qwen_tts"),
        "qwen_tts.core": ModuleType("qwen_tts.core"),
        "qwen_tts.core.models": core_models,
        "qwen_tts.core.models.modeling_qwen3_tts": model_module,
        "qwen_tts.inference": ModuleType("qwen_tts.inference"),
        "qwen_tts.inference.qwen3_tts_tokenizer": tokenizer_module,
        "qwen_tts.inference.qwen3_tts_model": wrapper_module,
    }.items():
        monkeypatch.setitem(sys.modules, key, value)

    runtime.install_mixed_device_support()
    wrapped_func = Tokenizer.from_pretrained.__func__
    runtime.install_mixed_device_support()
    assert Tokenizer.from_pretrained.__func__ is wrapped_func
    assert Base().device == torch.device("cuda:0")
    assert Talker().device == torch.device("cuda:0")
    for protected in (
        "Qwen3TTSDecoderLayer",
        "Qwen3TTSTalkerDecoderLayer",
        "Qwen3TTSTalkerCodePredictorModelForConditionalGeneration",
    ):
        assert protected in Talker._no_split_modules
    tokenizer = Tokenizer.from_pretrained("dummy", device_map="auto")
    assert Tokenizer.last_kwargs["device_map"] == "cpu"
    assert tokenizer.device == torch.device("cuda:0")
    assert Wrapper(Base(), "processor").device == torch.device("cuda:0")


def test_reference_failure_has_precise_stage_without_private_text(tmp_path, monkeypatch):
    pytest.importorskip("torch")
    sf = pytest.importorskip("soundfile")
    from studio.engine import QwenEngine, InferencePhaseError
    from studio.schema import Generate

    import studio.engine as engine_module
    monkeypatch.setattr(engine_module, "cancellable_talker", lambda model, event: nullcontext())
    transformers = ModuleType("transformers")
    transformers.set_seed = lambda seed: None
    monkeypatch.setitem(sys.modules, "transformers", transformers)

    reference = tmp_path / "reference.wav"
    sf.write(str(reference), np.zeros(2400, dtype=np.float32), 24000)
    engine = QwenEngine(tmp_path)

    class FakeWrapper:
        def create_voice_clone_prompt(self, **kwargs):
            assert kwargs["ref_audio"][1] == 24000
            raise ValueError("Private transcript must never appear in UI or logs")

    engine.model = FakeWrapper()
    request = Generate(
        model_id="fake", mode="clone", text="Demo", language="Chinese",
        reference_id="a" * 32, consent=True, ref_text="example transcript",
    )
    with pytest.raises(InferencePhaseError) as raised:
        engine.generate(request, "Demo", reference, threading.Event())
    assert raised.value.phase == "reference_encoding"
    from studio.privacy import public_error, failure_details
    _, message = failure_details(raised.value, raised.value.phase)
    assert "Private transcript" not in public_error(raised.value, stage=raised.value.phase)
    assert "Private transcript" not in message
    assert "Reference" in message


def test_standalone_package_needs_no_external_webui_checkout():
    root = Path(__file__).resolve().parents[1]
    assert (root / "studio" / "inference_runtime.py").is_file()
    assert (root / "requirements-inference.txt").is_file()
    assert not (root / "setup-engine.ps1").exists()
    assert not (root / "requirements-engine.txt").exists()
    for path in (root / "install.ps1", root / "start.ps1"):
        contents = path.read_text(encoding="utf-8")
        assert "git clone" not in contents
        assert "EngineRoot" not in contents
    assert "licyk" not in (root / "README.md").read_text(encoding="utf-8").split("## UI")[0]
