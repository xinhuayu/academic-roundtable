$ErrorActionPreference = 'Stop'

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$python = Join-Path $projectRoot '.venv\Scripts\python.exe'

if (-not (Test-Path -LiteralPath $python)) {
    throw 'The local virtual environment is missing. Run scripts\setup.ps1 first.'
}

Set-Location $projectRoot
& $python -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8765
