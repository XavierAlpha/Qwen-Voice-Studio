[CmdletBinding()]
param([Alias('Python')][string]$PythonPath = '')
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) { throw 'uv is required (https://docs.astral.sh/uv/).' }
if (-not $PythonPath) {
    $Candidates = @((Join-Path $PSScriptRoot '.venv\Scripts\python.exe'))
    if ($env:VIRTUAL_ENV) { $Candidates += (Join-Path $env:VIRTUAL_ENV 'Scripts\python.exe') }
    $Candidates += (Join-Path (Split-Path $PSScriptRoot -Parent) '.venv\Scripts\python.exe')
    $PythonPath = $Candidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
}
if (-not $PythonPath) {
    & uv venv --python 3.12 .venv
    if ($LASTEXITCODE -ne 0) { throw 'Could not create the Python environment.' }
    $PythonPath = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
}
if (-not (Test-Path -LiteralPath $PythonPath)) { throw 'PythonPath does not exist.' }
$PythonPath = (Resolve-Path -LiteralPath $PythonPath).Path
& $PythonPath -c "import sys; assert (3,12) <= sys.version_info[:2] < (3,14), 'Python 3.12 or 3.13 is required'"
if ($LASTEXITCODE -ne 0) { throw 'Unsupported Python version.' }

# Install PyTorch only when missing. Automatic backend selection chooses CUDA
# when supported, otherwise CPU. Never silently replace existing CUDA wheels.
& $PythonPath -c "import importlib.util; assert importlib.util.find_spec('torch') is not None"
if ($LASTEXITCODE -ne 0) {
    & uv pip install --python $PythonPath --torch-backend=auto torch torchaudio
    if ($LASTEXITCODE -ne 0) { throw 'Could not install PyTorch. See https://pytorch.org/get-started/locally/.' }
}

New-Item -ItemType Directory -Force '.local' | Out-Null
$Constraint = Join-Path $PSScriptRoot '.local\runtime-constraints.txt'
# Snapshot only the already-installed PyTorch family; Qwen dependencies may
# need a compatible HF Hub/Transformers version, which uv should resolve.
$Code = @'
import importlib.metadata as metadata
from pathlib import Path
names = ('torch','torchaudio','torchvision')
lines = []
for name in names:
    try: lines.append(f'{name}=={metadata.version(name)}')
    except metadata.PackageNotFoundError: pass
Path('.local/runtime-constraints.txt').write_text('\n'.join(lines)+'\n', encoding='utf-8')
'@
& $PythonPath -c $Code
if ($LASTEXITCODE -ne 0) { throw 'Could not record the existing inference environment.' }
& uv pip install --python $PythonPath --torch-backend=auto --constraint $Constraint -r requirements-ui.txt -r requirements-inference.txt
if ($LASTEXITCODE -ne 0) { throw 'Dependency resolution failed. Your existing CUDA wheels were preserved; see README.' }
& uv pip check --python $PythonPath
if ($LASTEXITCODE -ne 0) { throw 'Dependency conflicts remain; inspect the displayed uv report.' }
[System.IO.File]::WriteAllText((Join-Path $PSScriptRoot '.local\python-path.txt'), $PythonPath)
Write-Host 'Qwen Voice Studio installed. No external WebUI or inference repository is required.'
Write-Host 'Run .\start.ps1'
