@echo off
title ForexAI - Sync Upload
color 0B
cd /d d:\forexAI

echo.
echo  =============================================
echo       ForexAI Data Upload to Google Drive
echo  =============================================
echo.

call venv\Scripts\activate
python scripts\sync_upload.py

echo.
pause
