"""Execution-device diagnostics adapted from licyk/qwen-tts-webui.
Source: qwen_tts_webui/qwen_tts/device_utils.py (main, inspected 2026-11-05).
Copyright licyk and contributors. Distributed under GPL-3.0; see LICENSE.
Adaptation: read-only diagnostics, explicitly ignores meta hook devices.
The companion in-tree inference_runtime module applies device corrections to the installed official Qwen library at runtime.
"""
import torch


def _as_device(value):
    return torch.device("cuda", value) if isinstance(value, int) else torch.device(value)


def hook_device(module):
    hook = getattr(module, "_hf_hook", None)
    if hook is None:
        return None
    for child in getattr(hook, "hooks", None) or [hook]:
        value = getattr(child, "execution_device", None)
        if value is not None:
            device = _as_device(value)
            if device.type != "meta":
                return device
    return None


def execution_device(module):
    """Do not confuse offloaded storage placeholders with compute devices."""
    own = hook_device(module)
    if own is not None:
        return own
    for iterator in (module.parameters(), module.buffers()):
        for tensor in iterator:
            if tensor.device.type != "meta":
                return tensor.device
    for child in module.modules():
        device = hook_device(child)
        if device is not None:
            return device
    return torch.device("cpu")
