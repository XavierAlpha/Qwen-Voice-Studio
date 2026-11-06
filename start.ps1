[CmdletBinding()]
param(
    [Alias('Python')][string]$PythonPath = '',
    [int]$Port = 7861,
    [string]$DataDir = '',
    [string]$ModelPath = '',
    [string]$ModelsRoot = ''
)
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
if (-not $PythonPath -and (Test-Path '.local\python-path.txt')) {
    $PythonPath = (Get-Content '.local\python-path.txt' -Raw).Trim()
}
if (-not $PythonPath) {
    $Candidates = @((Join-Path $PSScriptRoot '.venv\Scripts\python.exe'))
    if ($env:VIRTUAL_ENV) { $Candidates += (Join-Path $env:VIRTUAL_ENV 'Scripts\python.exe') }
    $Candidates += (Join-Path (Split-Path $PSScriptRoot -Parent) '.venv\Scripts\python.exe')
    $PythonPath = $Candidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
}
if (-not $PythonPath -or -not (Test-Path -LiteralPath $PythonPath)) { throw 'Run install.ps1 or provide -PythonPath.' }
$Arguments = @((Join-Path $PSScriptRoot 'app.py'), '--port', "$Port")
if ($DataDir) { $Arguments += @('--data-dir', $DataDir) }
if ($ModelPath) { $Arguments += @('--model', $ModelPath) }
if ($ModelsRoot) { $Arguments += @('--models-root', $ModelsRoot) }
& $PythonPath @Arguments
exit $LASTEXITCODE
