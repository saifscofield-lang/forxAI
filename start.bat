@echo off
title forxAI Launcher
color 0A
cd /d d:\forexAI

echo.
echo  =============================================
echo       ForexAI Trading Platform
echo  =============================================
echo.
echo  Starting services...
echo.

REM ── 1. Health Check ──
echo  [1/3] Running health check...
venv\Scripts\python scripts\health_check.py
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo  [!] Health check failed. Fix issues above before starting.
    echo.
    pause
    exit /b 1
)
echo.

REM ── 2. Start Trading Bot in a new window (auto-restart on crash) ──
echo  [2/3] Starting Trading Bot (Paper Trading + Telegram)...
start "forxAI Bot" cmd /k "cd /d d:\forexAI && venv\Scripts\activate && for /L %%x in () do (python scripts\paper_trade.py && exit /b || echo [!] Crashed. Restarting in 30s... && timeout /t 30 /nobreak)"

REM Wait 3 seconds for the bot to initialize
timeout /t 3 /nobreak >nul

REM ── 3. Start Streamlit Dashboard in a new window ──────────────────
echo  [3/3] Starting Dashboard...
start "forxAI Dashboard" cmd /k "cd /d d:\forexAI && venv\Scripts\activate && streamlit run dashboard\app.py"

REM Wait 4 seconds for Streamlit to start
timeout /t 4 /nobreak >nul

REM ── 3. Open browser automatically ────────────────────────────────
echo.
echo  Opening dashboard in browser...
start http://localhost:8501

echo.
echo  =============================================
echo   Both services are running!
echo.
echo   Dashboard  :  http://localhost:8501
echo   Bot logs   :  See "ForexAI Bot" window
echo.
echo   To stop: close both windows or run stop.bat
echo  =============================================
echo.
pause
