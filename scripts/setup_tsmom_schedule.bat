@echo off
:: Register the TSMOM daily scan in Windows Task Scheduler.
:: Run this as Administrator.
::
:: Schedule: 03:30 LOCAL daily (= 00:30 UTC for UTC+3 / Saudi/Egypt).
:: Adjust /st to your local equivalent of 00:30 UTC if your timezone
:: differs. The 30-minute offset after midnight UTC ensures the D1
:: bar has closed and broker has updated indicators.
::
:: To check:   schtasks /query /tn "ForexAI_TSMOM_Daily"
:: To run now: schtasks /run   /tn "ForexAI_TSMOM_Daily"
:: To remove:  schtasks /delete /tn "ForexAI_TSMOM_Daily" /f

schtasks /create ^
  /tn "ForexAI_TSMOM_Daily" ^
  /tr "D:\forexAI\scripts\run_tsmom_scan.bat" ^
  /sc daily ^
  /st 03:30 ^
  /rl highest ^
  /f

if %errorlevel%==0 (
    echo SUCCESS: ForexAI_TSMOM_Daily task created.
    echo Daily TSMOM scan will run at 03:30 local time.
    echo MT5 terminal must be running for the scan to succeed.
    echo.
    echo Verify:   schtasks /query /tn "ForexAI_TSMOM_Daily" /v /fo LIST
    echo Test now: schtasks /run   /tn "ForexAI_TSMOM_Daily"
) else (
    echo FAILED: Please run this script as Administrator.
    echo Right-click setup_tsmom_schedule.bat and select "Run as administrator".
)
pause
