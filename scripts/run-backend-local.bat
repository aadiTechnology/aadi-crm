@echo off
setlocal EnableExtensions
cd /d "%~dp0..\backend"

echo.
echo ============================================================
echo     CRM BACKEND  -  LOCAL
echo ============================================================
echo.

set "PYTHON=python"
if exist ".venv\Scripts\python.exe" set "PYTHON=.venv\Scripts\python.exe"

"%PYTHON%" -c "import uvicorn" >nul 2>&1
if errorlevel 1 (
    echo ERROR: uvicorn is not installed for %PYTHON%.
    echo From backend\, run:
    echo   python -m venv .venv
    echo   .venv\Scripts\pip install -e ".[dev]"
    exit /b 1
)

if not defined PLATFORM_API_BASE_URL set "PLATFORM_API_BASE_URL=http://127.0.0.1:8000"

netstat -ano | findstr /C:":8001 " | findstr "LISTENING" >nul
if not errorlevel 1 (
    echo ERROR: 127.0.0.1:8001 is already in use, so this start was refused.
    echo The CRM API is already running. Open http://127.0.0.1:8001/docs
    echo Or stop the existing process, then run this script again.
    exit /b 1
)

echo CRM API:        http://127.0.0.1:8001
echo Control Plane:  %PLATFORM_API_BASE_URL%
echo Docs:           http://127.0.0.1:8001/docs
echo Stop:           Ctrl+C
echo.
echo Use the same loopback host for the CRM page and both APIs.
echo localhost and 127.0.0.1 do not share the session cookie.
echo.

"%PYTHON%" -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8001
exit /b %ERRORLEVEL%
