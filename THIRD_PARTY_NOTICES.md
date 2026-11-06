# Attribution and third-party software

Qwen Voice Studio source is distributed under **GPL-3.0** (`LICENSE`). It
contains no private recordings, model weights, CUDA libraries, proprietary
fonts or bundled GitHub checkouts.

## In-tree mixed-device improvements

The design and relevant corrections in `studio/inference_runtime.py` and
`studio/device_utils.py` were adapted from the public project
[licyk/qwen-tts-webui](https://github.com/licyk/qwen-tts-webui), GPL-3.0:

- Use Accelerate's **execution-device hook** instead of a `meta` placeholder.
- Keep decoder layers and code predictor unsplit across devices.
- Keep the speech tokenizer on one real device during mixed offload.

These fixes are implemented in this repository and loaded at runtime without
cloning, installing, or referencing the licyk WebUI. Attribution for the
original Qwen code remains with Alibaba Qwen Team (Apache-2.0); the official
`qwen-tts` package is installed as a regular dependency, not vendored.

## Other references

- [QwenLM/Qwen3-TTS](https://github.com/QwenLM/Qwen3-TTS), Apache-2.0:
  model family definitions, VoiceDesign, Base voice clone and CustomVoice APIs.
- [ValyrianTech/Qwen3-TTS_server](https://github.com/ValyrianTech/Qwen3-TTS_server), MIT:
  modular local service architecture, reference only; no code copied.
- [Lucide](https://github.com/lucide-icons/lucide), ISC: icon consistency
  reference. The UI ships original inline SVG definitions, not the icon font.

Runtime dependencies (FastAPI, Uvicorn, PyTorch, Transformers, Accelerate,
NumPy, SoundFile, psutil, qwen-tts) remain ordinary separately installed
Python packages and retain their own respective licenses. Optional MP3 export
uses an already installed system FFmpeg executable. UI typography uses only
font stacks; no font binaries or web-font downloads are distributed.
