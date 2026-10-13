# Development mode: demo vendor and API with auto-reload in their own windows, Vite dev server (hot reload) in this one.
# Uses .venv\Scripts\python.exe when it exists (created by startup.bat), otherwise the python on PATH.
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$py = "python"
if (Test-Path ".venv\Scripts\python.exe") { $py = (Resolve-Path ".venv\Scripts\python.exe").Path }
$env:PYTHONUTF8 = "1"; $env:LITELLM_LOCAL_MODEL_COST_MAP = "True"; $env:LITELLM_TELEMETRY = "False"; $env:ADK_DISABLE_TELEMETRY = "1"

# the demo vendor back-office (simulated retailer system, reached over MCP); pass -NoVendor to skip it
if (-not ($args -contains "-NoVendor")) {
    $vendor = "Set-Location '$PSScriptRoot'; & '$py' -m uvicorn vendor_mock.app:app --reload --reload-dir vendor_mock --host 127.0.0.1 --port 8020"
    Start-Process powershell -ArgumentList "-NoExit", "-Command", $vendor
    $env:SENTINEL_DEFAULT_CONNECTOR_URL = "http://127.0.0.1:8020/mcp/"
}

$api = "Set-Location '$PSScriptRoot'; `$env:SENTINEL_DEFAULT_CONNECTOR_URL = '$env:SENTINEL_DEFAULT_CONNECTOR_URL'; & '$py' -m uvicorn app.main:app --app-dir backend --reload --reload-dir backend/app --host 127.0.0.1 --port 8000"
Start-Process powershell -ArgumentList "-NoExit", "-Command", $api

Write-Host "API: http://127.0.0.1:8000  |  UI: http://127.0.0.1:5173  |  Demo vendor: http://127.0.0.1:8020" -ForegroundColor Green
Set-Location "$PSScriptRoot\frontend"
npm run dev
