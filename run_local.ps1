$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    Write-Host "Opretter Python-miljoe..."
    python -m venv .venv
    & .\.venv\Scripts\pip.exe install -r requirements.txt
}

if (-not (Test-Path ".env")) {
    Write-Host "Mangler .env fil. Koer:"
    Write-Host "  copy .env.example .env"
    Write-Host "Rediger derefter .env og tilfoej din OPENAI_API_KEY."
    exit 1
}

Get-Content ".env" | ForEach-Object {
    if ($_ -match '^\s*#' -or $_ -match '^\s*$') { return }
    $parts = $_ -split '=', 2
    if ($parts.Count -eq 2) {
        Set-Item -Path "env:$($parts[0].Trim())" -Value $parts[1].Trim()
    }
}

$env:JAILA_SERVE_FRONTEND = "true"
if (-not $env:ANALYSE_LOGS_DIR) {
    $env:ANALYSE_LOGS_DIR = Join-Path $PSScriptRoot "data\analyse_logs"
}
if (-not $env:LEGAL_SOURCES_DIR) {
    $env:LEGAL_SOURCES_DIR = Join-Path $PSScriptRoot "data\legal_sources"
}
if (-not $env:FRONTEND_ORIGINS) {
    $env:FRONTEND_ORIGINS = "http://127.0.0.1:8010,http://localhost:8010"
}

New-Item -ItemType Directory -Force -Path $env:ANALYSE_LOGS_DIR | Out-Null
New-Item -ItemType Directory -Force -Path $env:LEGAL_SOURCES_DIR | Out-Null

Write-Host "Starter JAILA lokalt på http://127.0.0.1:8010/clean-start/index.html"
& .\.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8010 --reload
