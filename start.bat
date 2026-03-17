@echo off
REM Personal AI Assistant — Windows launcher
REM Double-click this file to start the assistant

cd /d "%~dp0"

REM Check if venv exists
if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] Virtual environment not found.
    echo Please run install.ps1 first:
    echo   Right-click install.ps1 ^> Run with PowerShell
    pause
    exit /b 1
)

REM Auto-update from git (keeps code in sync with latest fixes)
where git >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    echo Buscando actualizaciones...
    git pull --ff-only --quiet 2>nul
    if %ERRORLEVEL% EQU 0 (
        echo Codigo actualizado.
    ) else (
        echo Sin conexion o hay cambios locales. Continuando con version actual.
    )
)

echo.
echo Starting Personal AI Assistant...
echo Press Ctrl+C to stop.
echo.

.venv\Scripts\python.exe -m src.main

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [ERROR] Assistant exited with code %ERRORLEVEL%
    echo Check logs\ for details.
    pause
)
