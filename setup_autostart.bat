@echo off
REM ============================================================
REM  ForexAI Boot-on-Startup Setup (AI-018)
REM ============================================================
REM  Adds shortcuts to the Windows Startup folder so that:
REM    - start.bat        (engine + dashboard)
REM    - engine_watchdog  (monitoring)
REM  launch automatically when you log into Windows.
REM
REM  Run this script ONCE. Safe to re-run (overwrites existing shortcuts).
REM  Restart Windows or log out/in to test.
REM ============================================================

setlocal enabledelayedexpansion
title ForexAI Auto-Start Setup

set "STARTUP_DIR=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
set "PROJECT_DIR=%~dp0"
REM strip trailing backslash from PROJECT_DIR
if "%PROJECT_DIR:~-1%"=="\" set "PROJECT_DIR=%PROJECT_DIR:~0,-1%"

echo.
echo  =============================================
echo   ForexAI - Boot-on-Startup Setup
echo  =============================================
echo.
echo  Project dir : %PROJECT_DIR%
echo  Startup dir : %STARTUP_DIR%
echo.

if not exist "%STARTUP_DIR%" (
    echo  [ERROR] Startup folder not found at expected location.
    echo  Cannot proceed.
    pause
    exit /b 1
)

REM ============================================================
REM  Shortcut 1: ForexAI Bot + Dashboard (start.bat)
REM ============================================================
echo  [1/2] Creating shortcut: ForexAI Start...
powershell -NoProfile -Command ^
    "$ws = New-Object -ComObject WScript.Shell; ^
     $sc = $ws.CreateShortcut('%STARTUP_DIR%\ForexAI_Start.lnk'); ^
     $sc.TargetPath = '%PROJECT_DIR%\start.bat'; ^
     $sc.WorkingDirectory = '%PROJECT_DIR%'; ^
     $sc.WindowStyle = 7; ^
     $sc.Description = 'ForexAI engine + dashboard launcher'; ^
     $sc.Save()"
if errorlevel 1 (
    echo  [ERROR] Failed to create ForexAI_Start.lnk
) else (
    echo  [OK] %STARTUP_DIR%\ForexAI_Start.lnk
)

REM ============================================================
REM  Shortcut 2: ForexAI Watchdog
REM ============================================================
echo.
echo  [2/2] Creating shortcut: ForexAI Watchdog...
powershell -NoProfile -Command ^
    "$ws = New-Object -ComObject WScript.Shell; ^
     $sc = $ws.CreateShortcut('%STARTUP_DIR%\ForexAI_Watchdog.lnk'); ^
     $sc.TargetPath = '%PROJECT_DIR%\venv\Scripts\python.exe'; ^
     $sc.Arguments = 'scripts\engine_watchdog.py'; ^
     $sc.WorkingDirectory = '%PROJECT_DIR%'; ^
     $sc.WindowStyle = 7; ^
     $sc.Description = 'ForexAI engine watchdog (silent-detection + alerts)'; ^
     $sc.Save()"
if errorlevel 1 (
    echo  [ERROR] Failed to create ForexAI_Watchdog.lnk
) else (
    echo  [OK] %STARTUP_DIR%\ForexAI_Watchdog.lnk
)

echo.
echo  =============================================
echo   Setup complete.
echo.
echo   Shortcuts installed:
echo     - %STARTUP_DIR%\ForexAI_Start.lnk
echo     - %STARTUP_DIR%\ForexAI_Watchdog.lnk
echo.
echo   To test without rebooting:
echo     1. Run: explorer "%STARTUP_DIR%"
echo     2. Double-click each shortcut.
echo.
echo   To remove auto-start later:
echo     Delete both .lnk files from the Startup folder.
echo.
echo  =============================================
pause
