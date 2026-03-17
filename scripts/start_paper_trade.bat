@echo off
:: ForexAI Paper Trading - Auto-restart on crash/network failure
cd /d D:\forexAI
call venv\Scripts\activate.bat

:loop
echo ============================================
echo   ForexAI Paper Trading - Starting...
echo   %date% %time%
echo ============================================
echo.

python scripts\paper_trade.py

echo.
echo [!] Process stopped. Restarting in 30 seconds...
echo     Press Ctrl+C to stop completely.
echo.
timeout /t 30 /nobreak
goto loop
