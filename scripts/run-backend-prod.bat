@echo off
setlocal EnableExtensions
cd /d "%~dp0..\backend"

echo.
echo ============================================================
echo     CRM BACKEND  -  PRODUCTION
echo ============================================================
echo.

if not defined PLATFORM_API_BASE_URL (
    echo ERROR: PLATFORM_API_BASE_URL is not set.
    echo Set it to the Control Plane API origin before starting, for example:
    echo   set PLATFORM_API_BASE_URL=https://control-plane.example.com
    echo   scripts\run-backend-prod.bat
    exit /b 1
)

if not defined CRM_BIND_HOST set "CRM_BIND_HOST=0.0.0.0"
if not defined CRM_PORT set "CRM_PORT=8001"

set "PYTHON=python"
if exist ".venv\Scripts\python.exe" set "PYTHON=.venv\Scripts\python.exe"

"%PYTHON%" -c "import uvicorn" >nul 2>&1
if errorlevel 1 (
    echo ERROR: uvicorn is not installed for %PYTHON%.
    echo From backend\, run: python -m pip install -e .
    exit /b 1
)

netstat -ano | findstr /C:":%CRM_PORT% " | findstr "LISTENING" >nul
if not errorlevel 1 (
    echo ERROR: Port %CRM_PORT% is already in use.
    echo Stop the existing process, then run this script again.
    exit /b 1
)

echo CRM API:        http://%CRM_BIND_HOST%:%CRM_PORT%
echo Control Plane:  %PLATFORM_API_BASE_URL%
echo Reload:         off
echo Stop:           Ctrl+C
echo.
echo Browser origins are still the localhost list in backend\app\main.py.
echo A public CRM page needs that allowlist updated before this process can accept its browser calls.
echo.

"%PYTHON%" -m uvicorn app.main:app --host %CRM_BIND_HOST% --port %CRM_PORT%
exit /b %ERRORLEVEL%
