# Qwen Voice Studio 3.6

[简体中文](README.md) | [Architecture](docs/ARCHITECTURE.md) | [Review](docs/REVIEW.md) | [Notices](THIRD_PARTY_NOTICES.md)

A **self-contained local Qwen3-TTS application** with a modern bilingual WebUI, model discovery, serial inference queue, library and local CPU / single-GPU / hybrid CPU+GPU modes. FastAPI and native HTML/CSS/JavaScript; **no external WebUI checkout, backend-path configuration, Node.js build system or ComfyUI is required**.

The official `qwen-tts`, PyTorch, Transformers and Accelerate packages remain normal pip/uv dependencies. Model weights and GPU drivers are not bundled.

## Windows + uv

Extract the ZIP and run from PowerShell:

```powershell
.\install.ps1
.\start.ps1
```

The installer creates a Python 3.12 `.venv` when needed. To use an existing working Torch/CUDA environment:

```powershell
.\install.ps1 -PythonPath "..\.venv\Scripts\python.exe"
.\start.ps1
```

Open `http://127.0.0.1:7861`. `-ModelsRoot` and `-ModelPath` on `start.ps1` select local checkpoint locations. On an interactive **Windows host**, use **Settings → Models → Choose folder**, then **Add** to register the selected checkpoint. Open **Discovery options** and repeatedly use **Add folder** to append scan roots, remove individual entries, or edit the list manually. **Save & scan** first saves the updated search roots and then discovers models. The native dialog runs on the Windows computer running Studio, not on a remote browser client; non-Windows or non-interactive hosts keep manual path editing. The chooser requires built-in Windows PowerShell and an interactive desktop; no model files are uploaded by browsing. Discovery checks known model configs, weights and tokenizers; it never downloads weights or traverses the full disk.

Supported complete checkpoints: **VoiceDesign 1.7B**, **Base 0.6B / 1.7B** and **CustomVoice 0.6B / 1.7B**. Reference-audio cloning requires **Base**, consent, and normally an accurate transcript (unless using speaker-embedding-only mode). GGUF and LoRA are not supported by this runtime.

## Device modes

- **Auto** uses CUDA if available (BF16 when supported, otherwise FP32), or CPU if CUDA is unavailable. It never guesses required VRAM, preemptively blocks GPU use on weight estimates, switches silently based on free memory, or adjusts user budgets.
- **GPU** uses explicit FP32/BF16 where supported, with an experimental FP16 option.
- **GPU + CPU** uses FP32 and Accelerate placement with **in-tree mixed-device corrections** in `studio/inference_runtime.py` and `studio/device_utils.py`, credited in `THIRD_PARTY_NOTICES.md`. GPU/CPU weight budgets are user-entered and passed through without hardware-based clamping.
- **CPU** uses FP32 as the compatibility baseline.

All modes call the official installed Qwen Python package. No extra WebUI, Git clone, engine root or runtime downloader is needed. A user-entered GPU *weight* budget is not a global VRAM ceiling. Actual compatibility depends on the user's environment and is reported by the runtime, not guessed from hardware capacity.

Errors are classified into model loading, reference encoding, speech generation, and waveform validation without logging reference audio, transcripts or private paths. Harmless model initialization messages (`code_predictor_config is None`, etc.) are not treated as failures.

## v3.6 Windows folder selection and scan-root list

The model registration path can be filled using a Windows Explorer-style system folder chooser. Scan roots can be added individually by repeating the native picker; duplicates are ignored and paths may be removed independently. The next picker opens near the previous selection. A compact editable list and optional multi-line manual editor replace the always-visible large text box. A canceled picker makes no changes. Save & scan applies only discovery settings before scanning, leaving unsubmitted edits on other Settings tabs pending. Paths persist as part of the existing model-roots configuration. The dialog is invoked by the loopback, token-protected API and runs **on the Studio host**; it cannot pick a directory from a remote browser machine. Manual editing remains available everywhere.

## v3.5 compact model UI, typography and refresh restoration

The sidebar Local models section is reduced to a model selector, short model detail and unobtrusive Manage link. Settings → Models lists models and offers registration/discovery, while seldom-used search roots and scan-depth controls are collapsed. The Appearance font selector now uses two compact horizontal rows in the existing design system rather than oversized sample tiles. Reviewed at desktop and 320–1920 px widths in both languages.

Mode, model, speaker, generation language and sampling controls, take count, line/segment options, playback/export choices, library filters and all visual preferences are remembered across refresh. Unsaved model/runtime settings also survive a refresh **within the current tab**; pressing Save from any Settings tab applies them, while Cancel discards them.

For privacy, text, voice instructions, reference transcripts and reference identifiers are saved to this tab's **`sessionStorage`** by default, not persistent `localStorage`. This allows reload recovery without enabling cross-session draft retention. Enabling **Settings → Privacy → Keep drafts** moves them to durable local browser storage; disabling it moves them back and removes durable copies. Browser session restore and backups may also retain session data, so use Clear Site Data for sensitive text. Consent to reuse a reference voice is **never restored automatically**. On reload the app verifies reference metadata through its local API and removes stale references.

## v3.4 UX, speaker selection, diagnostics

The home screen has one global Settings entry. Density, layout, theme, and type are in **Settings → Appearance**. Generating automatically loads/reuses the selected checkpoint; manual **Unload model** is an optional action in **Settings → Inference** that does not remove model files. Advanced **Number of takes** means independent audio outputs (1–3), *not* model versions.

CustomVoice speakers are read from the registered checkpoint's `talker_config.spk_id`, with a clear empty state for missing/incompatible models. UI notifications are deduplicated and capped at three; successes expire after about 3.5 seconds, failures after 8.5 seconds, and form validation errors after 10 seconds. Errors remain available in job records. Inference choices and budgets are not automatically overridden or hardware-limited; runtime failures produce categorized diagnostics.

Backend settings are written only when changed; model discovery is refreshed when scan preferences change. Prior local data/installation compatibility is retained. No real-GPU or real-checkpoint validation is claimed by the test-tone suite.

## v3.3 upgrade and recovery

Settings startup is isolated from model and preset bootstrap. Optional missing DOM fields no longer blank the workspace; the selected model type is recovered on refresh. Factory presets are restored when an older privacy-clear leaves the library empty, and a Restore defaults action is available without overwriting custom entries. Static UI assets use no-store caching and a release stamp. The visual language is system-native and Apple-inspired, with neutral surfaces, restrained blue emphasis, consistent spacing and adaptive layouts; no Apple branding or font files are included.

To reuse existing history and registered model paths, stop the previous version and point `-DataDir` at your **previous data directory**, or copy it after backing it up. A new extracted folder otherwise starts with its own `.local` directory. On the first browser visit after upgrading, `Ctrl+Shift+R` can force-reload stale cached assets.

## UI and privacy

Chinese/English locale, local sans/editorial font stacks, light/dark/system theme, adjustable split/stacked layout, mobile view, presets, reference audio and microphone input, queue, waveform player, local history, WAV/FLAC and optional FFmpeg MP3 export.

The server listens only on loopback and is intended for a **single trusted local user**, not internet exposure. Local recordings and history are **not encrypted**. Cross-session draft retention is disabled by default; the current tab retains draft text through reload using sessionStorage. Use reference voices only with permission.

## Release quality

Three review passes cover inference/validation, bilingual responsive UI and security/stability/ZIP extraction. See `docs/REVIEW.md` and `docs/TARGET_ACCEPTANCE.md`. Synthetic inference/browser tests cannot establish real Qwen/CUDA/Windows performance or audio quality; perform acceptance on your own device. GPL-3.0 source, third-party licensing remains separate. No model weights, personal information or font binaries are distributed.
