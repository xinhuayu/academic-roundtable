$ErrorActionPreference = 'Stop'

$projectRoot = Split-Path -Parent $PSScriptRoot
$venvPython = Join-Path $projectRoot '.venv\Scripts\python.exe'

if (-not (Test-Path -LiteralPath $venvPython)) {
    $py = Get-Command py -ErrorAction SilentlyContinue
    $python = Get-Command python -ErrorAction SilentlyContinue
    if ($py) {
        & $py.Source -3 -m venv (Join-Path $projectRoot '.venv')
    } elseif ($python) {
        & $python.Source -m venv (Join-Path $projectRoot '.venv')
    } else {
        throw 'Python 3.11 or newer is required.'
    }
}

& $venvPython -m pip install -r (Join-Path $projectRoot 'requirements.txt')

$frontend = Join-Path $projectRoot 'frontend'
$pnpm = Get-Command pnpm -ErrorAction SilentlyContinue
$npm = Get-Command npm -ErrorAction SilentlyContinue
if ($pnpm) {
    & $pnpm.Source --dir $frontend install
    & $pnpm.Source --dir $frontend build
} elseif ($npm) {
    Push-Location $frontend
    try {
        & $npm.Source install
        & $npm.Source run build
    } finally {
        Pop-Location
    }
} else {
    throw 'Node.js with pnpm or npm is required.'
}

Write-Host 'Academic Roundtable is ready. Run .\run.ps1 from the project folder.'
