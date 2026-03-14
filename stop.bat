@echo off
title ForexAI Stop
color 0C
echo.
echo  Stopping ForexAI services...
echo.

REM Kill Streamlit
taskkill /FI "WINDOWTITLE eq ForexAI Dashboard*" /T /F >nul 2>&1

REM Kill Trading Bot
taskkill /FI "WINDOWTITLE eq ForexAI Bot*" /T /F >nul 2>&1

REM Kill any remaining streamlit or python processes from this project (optional)
REM taskkill /IM streamlit.exe /F >nul 2>&1

echo  All ForexAI services stopped.
echo.
pause
