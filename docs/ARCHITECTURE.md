# Architecture and operating contract

## Boundary

One local user, one process per data directory, one inference worker. Bind only to
127.0.0.1. This is not an Internet-facing service or an execution sandbox. Model
weights must come from a trusted source.

## Modules

- `app.py`: process lock, private rotating log, offline flags, loopback Uvicorn.
- `studio/config.py`: typed settings; atomic config replacement; explicit roots.
- `studio/models.py`: bounded discovery, task/capability extraction, shard and
  tokenizer validation; no Torch import, downloads or remote model code execution.
- `studio/engine.py`: lazy backend import, capability-only automatic device selection, single
  model instance, reference prompt LRU (3 entries), cooperative cancellation.
- `studio/inference_runtime.py`: in-tree Accelerate execution-device and decoder-placement corrections.
- `studio/device_utils.py`: execution-device diagnostics, ignoring meta storage.
- `studio/jobs.py`: bounded queue (32 pending), durable status, restart recovery,
  segmentation, atomic result/terminal-job transaction, interrupted-task cleanup.
- `studio/store.py`: SQLite WAL; bound queries and paginated history.
- `studio/audio.py`: finite waveform checks, safe peak limiting, atomic writes,
  bounded reference decoding and optional FFmpeg exports.
- `studio/files.py`: leases protect audio responses from concurrent deletion.
- `studio/server.py`: same-origin API, request limits, preferences and privacy API.
- `ui/`: framework-free ES modules; settings separate from creation/playback.
- `tests/`: synthetic engine and small metadata fixtures; no real model weights.

## Model discovery

Canonical paths deduplicate registration. Detection uses `model_type=qwen3_tts`,
`tts_model_type`, `tts_model_size`, `tokenizer_type` and `talker_config` instead of
folder naming. Known official combinations: Base 0.6B/1.7B, CustomVoice 0.6B/1.7B,
VoiceDesign 1.7B. Unknown model tasks are not enabled. Config-compatible fine-tuned
checkpoints still require separate inference validation.

A safetensors header check reads up to 8 MiB, validates offsets against file size,
and verifies required sharded files. It does not hash multi-GB tensor contents or
prove model semantics. Git LFS pointer files are rejected. Text tokenizer and
speech tokenizer are required. No pickle-only, GGUF, standalone adapter or
unknown quantization backend is enabled by this adapter.

Default roots: project `models`, parent `models`, local HF Hub cache. Respect
HF_HUB_CACHE/HUGGINGFACE_HUB_CACHE/HF_HOME. Descend at most configured depth (6 by
default), 4096 visited directories, approximately 8 seconds of traversal; slow
filesystem calls and registered-model revalidation can exceed that time budget.
Directory symlinks/junctions are not implicitly traversed; explicit roots and HF
file links are supported. Missing roots do not trigger a download.

## Inference and cancellation

The installed official `qwen-tts` package provides model APIs for CPU and GPU.
Qwen Voice Studio implements its own mixed-device execution fixes in
`studio/inference_runtime.py` and `studio/device_utils.py` (with GPL-3.0 source
attribution). No external WebUI or Git checkout is required. Runtime does not
fetch code, update dependencies, enable FlashAttention or enable CUDA Graph.

Auto mode selects BF16 GPU if supported, otherwise FP32 GPU if CUDA is available,
otherwise CPU. It never consults free VRAM/model weight estimates to decide or
silently switches to CPU/offload. Explicit runtime selections and GPU/CPU weight
budgets are passed unchanged; unsupported device capabilities and actual
allocation errors are reported. Requested and resolved runtime plus reason are
reported separately. FP16 remains an explicit experimental choice.

The public Qwen wrapper can discard `stopping_criteria`. Cancellation is therefore
injected at the specific model instance's `talker.generate`, under the engine
lock, restored in `finally`. Loading and running CUDA kernels cannot be forcibly
interrupted; cancellation is observed at generation/segment boundaries. No global
Transformers methods or files in site-packages are patched.

## Data and locks

Data is in `.local` or an explicit `--data-dir`. Startup locks the directory.
History survives restarts; unfinished tasks become interrupted rather than
silently replaying. Queue submission, cancellation and final commit use a common
job lock. File leases reject delete/clear while an audio response is in flight;
writers use temporary files and atomic replacement. A broken write deletes its
partial file. Generated audio and its metadata are not encrypted.

## API summary

Read-only bootstrap provides a session token; writes require X-Studio-Token and
same origin. GET /api/health, /api/models, /api/system, /api/history,
/api/preferences and /api/diagnostics support local tools. POST /api/jobs returns
a durable task ID; POST /api/jobs/{id}/cancel is cooperative. Privacy clearing
requires explicit X-Confirm-Clear plus the session token and an idle engine.

No cloud API, network listen-address setting or model downloader is provided.
The app does not clone backend Git code at installation or runtime. The normal Python
package installer obtains declared dependencies from configured package indexes.

## Frontend 3.4

- `bootstrap.js`: validates browser preferences before CSS to avoid theme flashes.
- `i18n.js` + `locales/`: one-time dictionary load, safe labels and factory-preset display.
- `appearance.js`: one validated source for font/theme/scale/density/layout; immediate
  local preview and DOM-correct placement of stacked actions.
- `navigation.js`: responsive sidebar, focus management and keyboard containment.
- `app.js`: workflow orchestration; current job signature and latest-history response guard.
- `player.js`: source identity caching prevents a favorite edit from interrupting playback.
- `styles.css`: shared design tokens, responsive/forced-color/reduced-motion behavior.

No database or inference API changes are required by localization. Browser preferences
use `qvs.*` and never enter exported generation parameters. UI language and synthesis
language are different settings. A Node runtime is optional for frontend unit tests only.
