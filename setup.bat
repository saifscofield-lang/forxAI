@echo off
title ForexAI Setup
color 0B
cd /d D:\forexAI

echo.
echo  =============================================
echo       ForexAI - Setup
echo  =============================================
echo.

REM 1. Create virtual environment
echo  [1/4] Creating virtual environment...
if not exist "venv" (
    python -m venv venv
    echo        Done.
) else (
    echo        Already exists - skipping.
)

REM 2. Install dependencies
echo.
echo  [2/4] Installing dependencies...
venv\Scripts\pip install -r requirements/requirements_phase0.txt --quiet
venv\Scripts\pip install -r requirements/requirements_dev.txt --quiet
venv\Scripts\pip install fpdf2 arabic-reshaper python-bidi --quiet
echo        Done.

REM 3. Create .env if missing
echo.
echo  [3/4] Checking .env file...
if not exist ".env" (
    copy .env.example .env >nul
    echo        Created .env from .env.example
    echo        IMPORTANT: Edit .env with your MT5 credentials!
) else (
    echo        .env already exists - skipping.
)

REM 4. Create data directories
echo.
echo  [4/4] Creating data directories...
if not exist "data\logs" mkdir data\logs
if not exist "data\raw" mkdir data\raw
if not exist "data\models" mkdir data\models
if not exist "data\reports" mkdir data\reports
if not exist "data\ml_training" mkdir data\ml_training
echo        Done.

echo.
echo  =============================================
echo   Setup complete!
echo.
echo   Next steps:
echo   1. Edit .env with your MT5 credentials
echo   2. Open MetaTrader 5 terminal
echo   3. Run health_check.bat to verify
echo   4. Run start.bat to begin trading
echo  =============================================
echo.
pause
