@echo off
title ForexAI Stop
color 0C
cd /d d:\forexAI

echo.
echo  =============================================
echo       ForexAI — Stopping Services
echo  =============================================
echo.

REM ── Close ForexAI CMD windows ──
echo  Closing ForexAI Bot window...
taskkill /FI "WINDOWTITLE eq ForexAI Bot*" /FI "IMAGENAME eq cmd.exe" /F >nul 2>&1

echo  Closing ForexAI Dashboard window...
taskkill /FI "WINDOWTITLE eq ForexAI Dashboard*" /FI "IMAGENAME eq cmd.exe" /F >nul 2>&1

echo.
echo  =============================================
echo   Done. All ForexAI windows closed.
echo  =============================================
echo.
pause
