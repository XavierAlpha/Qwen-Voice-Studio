## 3.6.0 — Native Windows folder selection, sequential scan roots and regression review

- Add a protected local `/api/native/folder` endpoint that opens an interactive Windows Explorer-style folder picker via a STA PowerShell/WinForms subprocess. No user path is interpolated into code; the selected local folder is returned without reading or uploading model contents. Non-Windows/headless hosts keep the manual field.
- Add a **Choose folder** action for direct model registration and a **repeated Add folder** action for scanning root directories. Show a compact removable directory list, preserve the optional multi-line editor, apply visual private-path masking and ignore duplicate Windows path spellings.
- **Save & scan** now applies discovery-path edits before executing discovery; changes to other tabs remain pending. Native dialog cancellation leaves form fields unchanged, and reopened dialogs do not accept late results from prior dialogs.
- Maintain existing model inference choices, user-entered device budgets, reference voice consent, draft privacy and data layout. Extend allowed configured scan roots to 128 (no device capability inference).
- Regression: mock folder picker API/CSRF/origin/errors, browser selection/registration/duplicate/cancel/remove/save/reload/layout, full Python/JS/browser suites. Real Windows UI behavior requires manual acceptance on an interactive Windows desktop.

# Changelog

## 3.5.0 - 2026-11-05

- Redesign the Local models sidebar as a minimal selector and Manage shortcut, simplify model rows, and collapse rarely used discovery controls in Settings.
- Replace oversized typeface sample cards with two compact horizontal font choices and review spacing/responsive overflow on desktop and narrow screens.
- Restore per-mode model, CustomVoice speaker, generation options, advanced segmentation/take count, playback/export, library filters and view choices across browser reloads.
- Keep authored text, voice instructions, reference transcripts and reference IDs in per-tab session storage by default; opt-in cross-session retention uses local browser storage, with migration/removal on toggle.
- Preserve unsaved model/runtime settings when the same tab reloads; Save from any Settings section commits changes, Cancel discards unsaved changes.
- Validate restored reference audio metadata against the backend; remove missing references instead of leaving an unusable player. Reference-voice authorization is never implicitly restored.
- Add reference metadata read-only API and synthetic browser persistence/layout regression suite, expanding release tests without altering inference dependencies or model resource policies.


## 3.1.0 - 2026-11-05

- Add Simplified Chinese and English dictionaries with browser preference detection,
  localized dynamic controls, singular counts and explicit starter examples.
- Add two local-only type systems, text scale, system theme and live Appearance preview.
- Replace layered legacy CSS with shared spacing, typography, color and control tokens.
- Keep user content, speech language, reference consent and playback intact on translation.
- Move Generate before Preview in stacked layouts using DOM order, not CSS visual order.
- Add keyboard-trapped mobile navigation, restore focus, reduced-motion and visible focus.
- Avoid rebuilding unchanged task buttons and reloading audio for favorite/name edits.
- Ignore stale history responses and preserve selected speaker on locale changes.
- Retain local discovery, privacy, queue and inference contracts from 3.0.
- Add frontend/unit/contrast contracts and bilingual responsive browser coverage.
- No schema migration, model download, inference dependency upgrade or font distribution.

## 3.2.0 - 2026-11-05

- Make inference self-contained: in-tree execution-device, unsplit decoder and speech tokenizer handling; no separate WebUI checkout, path or setup script.
- Install official Qwen runtime dependencies with uv, while preserving previously installed Torch/CUDA wheels.
- Validate reference text and Base model before enqueueing; expose privacy-safe failure phase and correlation reference.
- Normalize button/icon/text gaps, editor and reference field heights, preview actions, settings grids and mobile wrapping.
- Add independent low-VRAM and cloning-phase regression tests and repeat three-stage release audit.

## 3.3.0 - 2026-11-05

- Fix settings opening errors by making optional field initialization null-safe and decoupling workspace bootstrap from settings/hardware startup.
- Restore model and preset state after refresh; recover the first available compatible model type when the previous mode has no installed model.
- Heal a previously emptied factory preset database on restart; add an explicit non-destructive Restore defaults action.
- Make HTML/JS/CSS non-cacheable across in-place upgrades and version the entry scripts/styles.
- Rework styling toward a modern native-app appearance: neutral surfaces, macOS-inspired typography, restrained blue actions, rounded segmented controls, glass-like header, stable spacing and responsive layouts.
- Add dedicated backend recovery regressions and browser tests for settings, presets and model reinitialization.
- Preserve local-only, offline-first single-user architecture and existing inference engine without changing model dependencies.

## 3.4.0 - 2026-11-05

- Remove duplicate Settings button, home density/layout/theme toggles, redundant output layout control, and explicit model Load action. Keep optional model Unload in Settings → Inference.
- Move Number of takes and per-line batching into advanced generation settings; explain that each take is an independent audio result.
- Make CustomVoice speaker selector responsive to checkpoint metadata, with localized speaker descriptions, persisted selection, and clear missing-model/empty-speaker states.
- Do not preemptively block or reroute GPU operations by estimated model size/free VRAM. Automatic mode relies on CUDA/BF16 support only, and hybrid budgets are passed unchanged.
- Categorize allocation/shape/reference/loading/generation errors, deduplicate toast notices, cap visible notices at three, and expire temporary errors.
- Preserve existing project files and schemas. Extend Python/static/browser tests and regenerate visual review artifacts.
