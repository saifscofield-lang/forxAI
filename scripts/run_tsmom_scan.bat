@echo off
:: ForexAI TSMOM daily scan — Phase 6 Step 3 Tier A
:: One-shot. Triggered daily by Windows Task Scheduler (see
:: setup_tsmom_schedule.bat). MT5 terminal must be running.
cd /d D:\forexAI
call venv\Scripts\activate.bat

echo ============================================
echo   ForexAI TSMOM Daily Scan
echo   %date% %time%
echo ============================================
echo.

python scripts\run_tsmom_scan.py
set RC=%ERRORLEVEL%

echo.
echo Exit code: %RC%
exit /b %RC%
