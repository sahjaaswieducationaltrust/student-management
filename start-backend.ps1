# Starts the FastAPI backend on http://127.0.0.1:8000
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot\backend

if (-not (Test-Path .\.venv)) {
    Write-Host 'Creating virtual environment...' -ForegroundColor Cyan
    python -m venv .venv
    .\.venv\Scripts\python.exe -m pip install --upgrade pip
    .\.venv\Scripts\python.exe -m pip install -r requirements.txt
}

if (-not (Test-Path .\.env)) {
    Write-Host 'Creating backend\.env from .env.example' -ForegroundColor Yellow
    Copy-Item .env.example .env
    Write-Host 'Set MONGODB_URI in backend\.env before continuing.' -ForegroundColor Yellow
}

.\.venv\Scripts\python.exe -m app.check_db
if ($LASTEXITCODE -ne 0) {
    Write-Host 'Database is not reachable — fix the connection above, then re-run.' -ForegroundColor Red
    exit 1
}

Write-Host 'API docs: http://127.0.0.1:8000/docs' -ForegroundColor Green
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
