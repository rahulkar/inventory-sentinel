# Builds the frontend and serves the whole app from one FastAPI process on http://127.0.0.1:8000
# Uses .venv\Scripts\python.exe when it exists (created by startup.bat), otherwise the python on PATH.
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$py = "python"
if (Test-Path ".venv\Scripts\python.exe") { $py = ".venv\Scripts\python.exe" }
$env:PYTHONUTF8 = "1"; $env:LITELLM_LOCAL_MODEL_COST_MAP = "True"; $env:LITELLM_TELEMETRY = "False"; $env:ADK_DISABLE_TELEMETRY = "1"

if (-not (Test-Path "frontend\node_modules")) {
    Write-Host "Installing frontend packages..." -ForegroundColor Cyan
    Push-Location frontend; npm install; Pop-Location
}
Write-Host "Building frontend..." -ForegroundColor Cyan
Push-Location frontend
npm run build
if ($LASTEXITCODE -ne 0) { Pop-Location; throw "Frontend build failed" }
Pop-Location

Write-Host "Starting Inventory Sentinel at http://127.0.0.1:8000  (Ctrl+C to stop)" -ForegroundColor Green
& $py -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000
