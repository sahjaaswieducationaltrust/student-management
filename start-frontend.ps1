# Starts the React dev server on http://localhost:5173
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot\frontend

if (-not (Test-Path .\node_modules)) {
    Write-Host 'Installing npm packages...' -ForegroundColor Cyan
    npm install
}

Write-Host 'App: http://localhost:5173' -ForegroundColor Green
npm run dev
