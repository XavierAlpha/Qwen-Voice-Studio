"""Shareable diagnostics: no user names, filesystem paths, tokens or transcripts."""
import importlib.metadata as md
import json
import platform

report = {"python": platform.python_version(), "os": platform.system(), "packages": {}}
for package in ("torch", "torchaudio", "transformers", "accelerate", "huggingface-hub", "qwen-tts", "fastapi", "soundfile", "numpy"):
    try:
        report["packages"][package] = md.version(package)
    except md.PackageNotFoundError:
        report["packages"][package] = None
try:
    import torch
    report["cuda"] = torch.cuda.is_available()
    report["torch_cuda_build"] = torch.version.cuda
    if report["cuda"]:
        report["compute_capability"] = torch.cuda.get_device_capability(0)
        report["vram_gib"] = round(torch.cuda.get_device_properties(0).total_memory / 1024**3, 1)
except Exception as error:
    report["hardware_check"] = type(error).__name__
print(json.dumps(report, indent=2))
