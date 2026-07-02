@echo off
setlocal enabledelayedexpansion

cd /d "%~dp0.."

set PYTHONPATH=%PYTHONPATH%;%~dp0..\src
rem SSLKEYLOGFILE can crash Python/OpenSSL on Windows with "no OPENSSL_Applink".
set "SSLKEYLOGFILE="

if not exist logs (
    mkdir logs
)

if exist .venv\Scripts\activate.bat (
    call .venv\Scripts\activate.bat
)

if exist .env (
    echo Loading environment from .env...
    for /f "usebackq tokens=*" %%a in (".env") do (
        set "line=%%a"
        if not "!line:~0,1!"=="#" (
            if not "!line!"=="" (
                set "!line!"
            )
        )
    )
)

if "%OPS_AGENT_PORT%"=="" (
    set "OPS_AGENT_PORT=8000"
)
set "VITE_API_PROXY_TARGET=http://127.0.0.1:%OPS_AGENT_PORT%"

echo Stopping processes on ports %OPS_AGENT_PORT% and 5173...
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":%OPS_AGENT_PORT%" ^| findstr "LISTENING"') do (
    taskkill /T /F /PID %%a 2>nul
)
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":5173" ^| findstr "LISTENING"') do (
    taskkill /T /F /PID %%a 2>nul
)

echo Starting Ops Agent Backend...
start /b python src\app\main.py >logs\backend.log 2>&1

echo Starting Ops Agent Frontend...
echo Frontend API proxy target: %VITE_API_PROXY_TARGET%
cd web
npm run dev

echo.
echo Frontend server started. Backend running in background.
echo Check logs\backend.log for backend logs.
echo Press Ctrl+C to stop servers
echo.
