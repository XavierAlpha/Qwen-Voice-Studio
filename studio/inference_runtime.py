"""Internal Qwen3-TTS execution fixes for Accelerate's mixed CPU/CUDA placement.

This is source inside Qwen Voice Studio, not an external WebUI checkout.
The three fixes follow the open-source implementation documented by
licyk/qwen-tts-webui: execution-device detection, no-split decoder groups,
and a non-sharded speech tokenizer. GPL-3.0 notices in THIRD_PARTY_NOTICES.md.

Qwen's official ``qwen-tts`` package remains a normal Python dependency;
models and Python/CUDA runtimes are not copied into the application.
"""
from __future__ import annotations

import threading
from .device_utils import execution_device

_LOCK = threading.Lock()
_PATCHED = False


def _patched_device(module):
    """Use the Accelerate hook's execution device, not offloaded meta storage."""
    return execution_device(module)


def install_mixed_device_support():
    """Apply narrowly scoped, idempotent in-process Qwen model fixes.

    Must run before ``Qwen3TTSModel.from_pretrained``.  Unlike modifying an
    installed package on disk, this does not change the user's Python env.
    It is safe for subsequent CPU or single-GPU loads in the same process.
    """
    global _PATCHED
    if _PATCHED:
        return
    with _LOCK:
        if _PATCHED:
            return
        from qwen_tts.core.models import modeling_qwen3_tts as models
        from qwen_tts.inference.qwen3_tts_tokenizer import Qwen3TTSTokenizer
        from qwen_tts.inference.qwen3_tts_model import Qwen3TTSModel

        model_class = models.Qwen3TTSPreTrainedModel
        talker_class = models.Qwen3TTSTalkerTextPreTrainedModel
        for cls in (model_class, talker_class):
            cls.device = property(_patched_device)

        # Do not split attention/MLP or the tightly coupled code predictor.
        protected = (
            "Qwen3TTSTalkerDecoderLayer",
            "Qwen3TTSDecoderLayer",
            "Qwen3TTSTalkerCodePredictorModelForConditionalGeneration",
        )
        original = tuple(getattr(talker_class, "_no_split_modules", ()) or ())
        talker_class._no_split_modules = list(dict.fromkeys((*original, *protected)))
        original = tuple(getattr(model_class, "_no_split_modules", ()) or ())
        model_class._no_split_modules = list(dict.fromkeys((*original, *protected)))

        # The codec cannot be reliably auto-sharded with the model's talker
        # device map. Keep its encoder/decoder together on CPU in mixed mode.
        original_tokenizer = Qwen3TTSTokenizer.from_pretrained.__func__

        @classmethod
        def tokenizer_from_pretrained(cls, path, **kwargs):
            mapping = kwargs.get("device_map")
            if isinstance(mapping, dict) or mapping in ("auto", "balanced", "balanced_low_0", "sequential"):
                kwargs = dict(kwargs, device_map="cpu")
            instance = original_tokenizer(cls, path, **kwargs)
            instance.device = execution_device(instance.model)
            return instance

        Qwen3TTSTokenizer.from_pretrained = tokenizer_from_pretrained
        # The outer wrapper also caches device during construction. Property
        # fixes above must be in place before it observes ``model.device``.
        original_init = Qwen3TTSModel.__init__

        def wrapper_init(self, model, processor, generate_defaults=None):
            original_init(self, model, processor, generate_defaults)
            self.device = execution_device(model)

        Qwen3TTSModel.__init__ = wrapper_init
        _PATCHED = True


def mixed_device_available() -> bool:
    """A real, locally installable dependency check; no separate checkout."""
    from importlib.util import find_spec
    return find_spec("qwen_tts") is not None and find_spec("accelerate") is not None
