"""Interactive Windows folder selector, hosted by the *local app process*.

Browsers cannot expose absolute directory paths from a directory upload input.
Only the loopback API, protected by the application's per-process token, invokes
this picker. The service never reads or uploads the chosen directory itself.
"""
import base64
import binascii
import ctypes
import os
import platform
from pathlib import Path
import shutil
import subprocess
import threading


# FolderBrowserDialog with AutoUpgradeEnabled uses the modern Explorer-style
# directory picker on current Windows. Environment variables carry the optional
# initial directory; paths are never interpolated into PowerShell code.
_PICK_SCRIPT = r"""
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Windows.Forms
$folder = New-Object System.Windows.Forms.FolderBrowserDialog
$folder.AutoUpgradeEnabled = $true
$folder.ShowNewFolderButton = $true
$folder.Description = $env:QVS_PICKER_DESCRIPTION
$start = $env:QVS_PICKER_START
if ($start -and [System.IO.Directory]::Exists($start)) { $folder.SelectedPath = $start }
$owner = New-Object System.Windows.Forms.Form
$owner.TopMost = $true
$owner.ShowInTaskbar = $false
$owner.Opacity = 0
try {
    $owner.Show()
    [void]$owner.Activate()
    if ($folder.ShowDialog($owner) -eq [System.Windows.Forms.DialogResult]::OK) {
        [Console]::WriteLine([Convert]::ToBase64String([System.Text.Encoding]::UTF8.GetBytes($folder.SelectedPath)))
    }
} finally {
    $owner.Close()
    $owner.Dispose()
    $folder.Dispose()
}
"""


class PickerError(Exception):
    """Public, non-path-bearing folder picker errors."""


class PickerBusy(PickerError):
    """Another system folder dialog is still open."""


def _powershell():
    if platform.system() != "Windows":
        return None
    executable = Path(os.environ.get("SystemRoot", "C:\\Windows")) / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"
    if executable.is_file():
        return str(executable)
    return shutil.which("powershell.exe")


def _interactive_session():
    if platform.system() != "Windows":
        return False
    try:
        session = ctypes.c_ulong()
        if not ctypes.windll.kernel32.ProcessIdToSessionId(os.getpid(), ctypes.byref(session)):
            return False
        return session.value != 0  # Session 0 services have no visible user desktop.
    except (AttributeError, OSError):
        return False


class NativeFolderPicker:
    def __init__(self):
        self.lock = threading.Lock()

    def available(self):
        return bool(_powershell() and _interactive_session())

    def pick(self, purpose="model", initial_path=None):
        exe = _powershell()
        if not exe or not _interactive_session():
            raise PickerError("The Windows folder selector is unavailable in this session. Enter a path manually.")
        if not self.lock.acquire(blocking=False):
            raise PickerBusy("Another folder selector is open. Close it before choosing again.")
        try:
            start = None
            if initial_path:
                try:
                    candidate = Path(os.path.expandvars(initial_path)).expanduser()
                    if candidate.is_dir():
                        start = str(candidate.resolve())
                    elif candidate.is_file():
                        start = str(candidate.parent.resolve())
                except (OSError, ValueError):
                    pass
            env = os.environ.copy()
            env["QVS_PICKER_START"] = start or ""
            env["QVS_PICKER_DESCRIPTION"] = (
                "Choose a Qwen3-TTS model folder" if purpose == "model" else "Add a model scan folder"
            )
            try:
                result = subprocess.run(
                    [exe, "-NoProfile", "-STA", "-Command", _PICK_SCRIPT],
                    capture_output=True, text=True, encoding="ascii", errors="replace",
                    env=env, timeout=600,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                    check=False,
                )
            except (subprocess.TimeoutExpired, OSError) as exc:
                raise PickerError("The system folder selector could not be completed. Enter a path manually.") from exc
            if result.returncode:
                raise PickerError("The system folder selector failed. Enter a path manually.")
            encoded = result.stdout.strip()
            if not encoded:  # User pressed Cancel: not an error.
                return None
            try:
                selected = Path(base64.b64decode(encoded, validate=True).decode("utf-8"))
                if not selected.is_dir():
                    raise PickerError("The selected folder is not accessible. Choose another folder.")
                return str(selected.resolve())
            except (ValueError, UnicodeError, OSError, binascii.Error) as exc:
                raise PickerError("The selected folder could not be read. Enter a path manually.") from exc
        finally:
            self.lock.release()
