@echo off
title ForexAI - Sync Download
color 0D
cd /d d:\forexAI

echo.
echo  =============================================
echo       ForexAI Data Download from Google Drive
echo  =============================================
echo.

call venv\Scripts\activate
python scripts\sync_download.py

echo.
pause
