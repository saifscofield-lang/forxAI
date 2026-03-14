@echo off
title ForexAI Launcher
color 0A
cd /d d:\forexAI

echo.
echo  =============================================
echo       ForexAI Trading Platform
echo  =============================================
echo.
echo  Starting services...
echo.

REM ── 1. Start Trading Bot in a new window ─────────────────────────
echo  [1/2] Starting Trading Bot (Paper Trading + Telegram)...
start "ForexAI Bot" cmd /k "cd /d d:\forexAI && venv\Scripts\activate && python scripts\paper_trade.py"

REM Wait 3 seconds for the bot to initialize
timeout /t 3 /nobreak >nul

REM ── 2. Start Streamlit Dashboard in a new window ──────────────────
echo  [2/2] Starting Dashboard...
start "ForexAI Dashboard" cmd /k "cd /d d:\forexAI && venv\Scripts\activate && streamlit run dashboard\app.py"

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
