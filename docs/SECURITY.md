# Privacy, safety and deployment limits

## What the release contains

Source, installation scripts, tests, synthetic-test screenshots and audit results.
No personal username/home path, account token, user audio, job database, model
weights, virtual environment, external WebUI checkout, dependency cache or runtime logs.
SHA256SUMS.json inventories distributed files. `tools/release_check.py` verifies
hashes and rejects unexpected files; run it immediately after extraction.

## What running the app stores

The local history feature stores scripts, voice instructions, reference transcripts,
parameters and audio in `.local`. Model registration and settings necessarily keep
local model paths on the machine. These files are NOT encrypted. Use OS
permissions and full-disk encryption for sensitive work. Never upload `.local`,
`engine`, `.venv`, `models`, personal config or environment snapshots with bug reports.

Editor scripts, voice descriptions, reference transcripts and reference IDs are
saved in the current tab's sessionStorage by default to survive refresh. An
explicit persistence opt-in moves them to localStorage across browser sessions;
turning it off removes durable copies and returns them to sessionStorage. The
browser may keep sessionStorage across session/tab restoration or in backups,
so this is not a secure-deletion guarantee. The voice-consent checkbox is never
restored automatically. Model selections, generation parameters, layout/theme
and media/library preferences persist independently of private text drafts.
Private-path blur is a shoulder-surfing convenience, NOT encryption or access control.

Source audio filenames are discarded and replaced with random identifiers. Public
model lists omit absolute paths. Exported generation metadata omits scripts,
instructions, speaker/reference identifiers and paths. Diagnostics exports use an
allowlist of package versions, counts and coarse OS information. Job failures log
categories rather than exception contents. Log formatting additionally redacts
common tokens, home paths and email addresses; this is not a universal secret detector.
Third-party code can print independently to the terminal: review terminal captures
before sharing them.

## Deletion

The privacy action clears audio, references, tasks and presets, unloads model/reference
caches and compacts SQLite with secure_delete. It preserves weights, model registrations,
configuration and the selected interpreter. Normal audio deletion is not the same
as full creative-data clearing: other historical records can still refer to the text.
To remove all project-managed private state, stop the app and remove the chosen data
directory. To remove browser preferences, clear this site's storage. OS backups,
SSD wear-leveling and browser download caches cannot be securely erased by this app.

## Network boundary

Loopback only, trusted Host checks, blocked cross-site requests, per-process write
CSRF token, bounded bodies (128 KiB JSON / 25 MiB reference audio), no external CDN,
no analytics. HF/Transformers offline flags and local_files_only are set for inference.
The app does not need HF_TOKEN. This is application-level offline behavior, not a
network sandbox: use a firewall for a hard no-network policy on third-party code.

This is NOT authenticated multi-user hosting. A process or user already on the same
machine can access the API and files. Do not expose via a tunnel/reverse proxy without
an independently designed authentication, authorization and encryption layer. Keep
browser, Python dependencies and GPU drivers patched through a controlled process.

## Native Windows folder selection (v3.6)

The desktop folder picker is available only when Studio itself runs in an interactive Windows user session. A POST to `/api/native/folder` requires the same process token and same-origin restrictions as other writes. Requests are serialized so simultaneous dialogs cannot be opened. An STA Windows PowerShell process hosts the OS FolderBrowserDialog; its starting path is passed through the child environment rather than embedded into the PowerShell script. The browser receives only the chosen directory path, never a directory's contents. Cancel returns `{"path": null, "cancelled": true}` and does not change configuration. A noninteractive or non-Windows service returns an error and the UI retains manual path entry.

**Important:** when a browser connects remotely, the native picker selects folders on the *Windows server running Studio*, not on the remote client's machine. Do not expose the loopback-only application to a public proxy or hostile users. Do not put tokens, model paths, or private transcripts in bug screenshots or logs.

## Trusted inputs and code

Only load weights and installed Python dependencies you trust. Safetensors
structural checks are not malware analysis; dependency imports execute code.
The mixed-device code ships inside this repository and requires no external
WebUI checkout. Pin vetted uv package versions for repeated deployment. The
ZIP manifest checks source integrity but is not a cryptographic publisher
signature; no signed-provenance claim is made.

Only use reference voices with authorization. Consent confirmation is a workflow
control, not an automatic proof of authorization or a forensic detection system.

## Interface assets in 3.2

Both dictionaries, icons and scripts are local. Font stacks only reference fonts already
installed on the host; no binaries or font download service is shipped. Appearance and
UI language persist in localStorage independently from optional private drafts. Language
changes do not translate or resend authored content. No screenshots contain real voices.
