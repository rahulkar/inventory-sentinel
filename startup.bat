@echo off
setlocal EnableDelayedExpansion
REM ============================================================
REM  Inventory Sentinel - one-click init and start (Windows)
REM  Creates a virtual environment, installs Python and Node
REM  packages, builds the UI and starts the app on port 8000.
REM  Usage:  startup.bat [--no-browser] [--port 8000] [--dev]
REM ============================================================
cd /d "%~dp0"
set PORT=8000
set OPEN_BROWSER=1
set DEV=0
:args
if "%~1"=="" goto run
if /I "%~1"=="--no-browser" set OPEN_BROWSER=0
if /I "%~1"=="--dev" set DEV=1
if /I "%~1"=="--port" (set PORT=%~2& shift)
shift
goto args

:run
set PYTHONUTF8=1
set LITELLM_LOCAL_MODEL_COST_MAP=True
set LITELLM_TELEMETRY=False
set ADK_DISABLE_TELEMETRY=1
echo.
echo  Inventory Sentinel - starting up
echo  ---------------------
if not exist "requirements.txt" (
  echo  [error] requirements.txt not found - run this from the project folder
  goto fail
)

REM ---- Python
set PY=
REM the py launcher picks the newest installed CPython and skips the Microsoft Store stub
where py >nul 2>nul && set PY=py -3
if "%PY%"=="" (where python >nul 2>nul && set PY=python)
if "%PY%"=="" (
  echo  [error] Python 3.11+ was not found. Install it from https://www.python.org/downloads/ and tick Add to PATH.
  goto fail
)
%PY% -c "import sys; sys.exit(0 if (3, 11) <= sys.version_info[:2] <= (3, 14) else 1)" >nul 2>nul
if errorlevel 1 (
  for /f "delims=" %%v in ('%PY% -c "import sys; print(sys.version.split()[0])"') do set PYVER=%%v
  echo  [error] Python !PYVER! found, but Inventory Sentinel needs Python 3.11 to 3.14. Install one from https://www.python.org/downloads/
  goto fail
)
if exist ".venv\Scripts\python.exe" (
  .venv\Scripts\python.exe -c "import sys; sys.exit(0 if (3, 11) <= sys.version_info[:2] <= (3, 14) else 1)" >nul 2>nul
  if errorlevel 1 (
    echo  [1/5] .venv was made with an unsupported Python - recreating it ...
    rmdir /s /q .venv
  )
)
if not exist ".venv\Scripts\python.exe" (
  echo  [1/5] creating virtual environment .venv ...
  %PY% -m venv .venv || goto fail
) else (
  echo  [1/5] virtual environment .venv found
)
set VPY=.venv\Scripts\python.exe

echo  [2/5] installing Python packages - the first run takes a few minutes ...
"%VPY%" -m pip install --quiet --upgrade pip >nul 2>nul
"%VPY%" -m pip install --quiet -r requirements.txt || goto fail

REM ---- Node
where npm >nul 2>nul
if errorlevel 1 (
  echo  [error] Node.js / npm was not found. Install the LTS version from https://nodejs.org/ and re-run.
  goto fail
)
if not exist "frontend\node_modules" (
  echo  [3/5] installing frontend packages ...
  pushd frontend
  call npm install --silent || (popd & goto fail)
  popd
) else (
  echo  [3/5] frontend packages found
)

if "%DEV%"=="1" goto dev

echo  [4/5] building the UI ...
pushd frontend
call npm run build --silent || (popd & goto fail)
popd

echo  [5/5] starting Inventory Sentinel at http://127.0.0.1:%PORT%  (Ctrl+C to stop)
echo        The AI assistant is optional: connect a LiteLLM gateway later under Settings (gear, top right).
echo.
if "%OPEN_BROWSER%"=="1" start "" cmd /c "timeout /t 3 >nul & start "" http://127.0.0.1:%PORT%/"
"%VPY%" -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port %PORT%
goto end

:dev
echo  [4/5] starting the API with auto-reload in a second window ...
start "Inventory Sentinel API" cmd /k ""%VPY%" -m uvicorn app.main:app --app-dir backend --reload --reload-dir backend/app --host 127.0.0.1 --port %PORT%"
echo  [5/5] starting the UI dev server at http://127.0.0.1:5173  (Ctrl+C to stop)
if "%OPEN_BROWSER%"=="1" start "" cmd /c "timeout /t 4 >nul & start "" http://127.0.0.1:5173/"
pushd frontend
call npm run dev
popd
goto end

:fail
echo.
echo  Startup failed. See the message above.
pause
exit /b 1

:end
endlocal
