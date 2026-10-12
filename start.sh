#!/usr/bin/env bash
# ============================================================
#  Inventory Sentinel - one-click init and start (macOS / Linux)
#  Creates a virtual environment, installs Python and Node
#  packages, builds the UI and starts the app on port 8000.
#  Usage:  ./start.sh [--no-browser] [--port 8000] [--dev]
# ============================================================
set -euo pipefail
cd "$(dirname "$0")"

PORT=8000
OPEN_BROWSER=1
DEV=0
export PYTHONUTF8=1 LITELLM_LOCAL_MODEL_COST_MAP=True LITELLM_TELEMETRY=False ADK_DISABLE_TELEMETRY=1
while [[ $# -gt 0 ]]; do
  case "$1" in
    --no-browser) OPEN_BROWSER=0 ;;
    --dev) DEV=1 ;;
    --port) PORT="$2"; shift ;;
    *) echo "unknown option: $1"; exit 1 ;;
  esac
  shift
done

echo
echo " Inventory Sentinel - starting up"
echo " ---------------------"

PY=""
for c in python3 python; do
  if command -v "$c" >/dev/null 2>&1; then PY="$c"; break; fi
done
if [[ -z "$PY" ]]; then
  echo " [error] Python 3.11+ was not found. Install it (https://www.python.org/downloads/) and re-run."
  exit 1
fi
supported() { "$1" -c 'import sys; sys.exit(0 if (3, 11) <= sys.version_info[:2] <= (3, 14) else 1)' 2>/dev/null; }
if ! supported "$PY"; then
  # prefer a versioned interpreter if the default one is too old or too new
  for c in python3.14 python3.13 python3.12 python3.11; do
    if command -v "$c" >/dev/null 2>&1 && supported "$c"; then PY="$c"; break; fi
  done
fi
if ! supported "$PY"; then
  echo " [error] $("$PY" --version 2>&1) found, but Inventory Sentinel needs Python 3.11 to 3.14. Install one from https://www.python.org/downloads/"
  exit 1
fi
if [[ -x ".venv/bin/python" ]] && ! supported ".venv/bin/python"; then
  echo " [1/5] .venv was made with an unsupported Python - recreating it ..."
  rm -rf .venv
fi
if [[ ! -x ".venv/bin/python" ]]; then
  echo " [1/5] creating virtual environment .venv ..."
  "$PY" -m venv .venv
else
  echo " [1/5] virtual environment .venv found"
fi
VPY=".venv/bin/python"

echo " [2/5] installing Python packages (first run takes a few minutes) ..."
"$VPY" -m pip install --quiet --upgrade pip >/dev/null 2>&1 || true
"$VPY" -m pip install --quiet -r requirements.txt

if ! command -v npm >/dev/null 2>&1; then
  echo " [error] Node.js / npm was not found. Install the LTS version (https://nodejs.org/) and re-run."
  exit 1
fi
if [[ ! -d "frontend/node_modules" ]]; then
  echo " [3/5] installing frontend packages ..."
  (cd frontend && npm install --silent)
else
  echo " [3/5] frontend packages found"
fi

open_browser() {
  local url="$1"
  if [[ "$OPEN_BROWSER" == "1" ]]; then
    (sleep 3; if command -v open >/dev/null 2>&1; then open "$url"; elif command -v xdg-open >/dev/null 2>&1; then xdg-open "$url"; fi) >/dev/null 2>&1 &
  fi
}

if [[ "$DEV" == "1" ]]; then
  echo " [4/5] starting the API with auto-reload in the background ..."
  "$VPY" -m uvicorn app.main:app --app-dir backend --reload --reload-dir backend/app --host 127.0.0.1 --port "$PORT" &
  API_PID=$!
  trap 'kill $API_PID 2>/dev/null || true' EXIT
  echo " [5/5] starting the UI dev server at http://127.0.0.1:5173  (Ctrl+C to stop)"
  open_browser "http://127.0.0.1:5173/"
  (cd frontend && npm run dev)
  exit 0
fi

echo " [4/5] building the UI ..."
(cd frontend && npm run build --silent)

echo " [5/5] starting Inventory Sentinel at http://127.0.0.1:$PORT  (Ctrl+C to stop)"
echo "       The AI assistant is optional: connect a LiteLLM gateway later under Settings (gear, top right)."
echo
open_browser "http://127.0.0.1:$PORT/"
exec "$VPY" -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port "$PORT"
