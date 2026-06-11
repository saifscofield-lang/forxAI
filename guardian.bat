@echo off
title Guardian - Methodology Lab
color 0B
cd /d d:\forexAI

:menu
cls
echo.
echo  =============================================
echo       GUARDIAN - Methodology Lab
echo  =============================================
echo.
echo   Guardian is an ON-DEMAND research tool.
echo   It does NOT trade and does NOT run continuously.
echo.
echo   [1]  Health check    (acceptance test - must be green)
echo   [2]  Judge a strategy (verdict on a submission JSON)
echo   [3]  New example      (copy the template to edit)
echo   [4]  Exit
echo.
set /p choice="  Choose [1-4]: "

if "%choice%"=="1" goto health
if "%choice%"=="2" goto judge
if "%choice%"=="3" goto example
if "%choice%"=="4" exit /b 0
goto menu

:health
echo.
echo  Running acceptance test...
echo.
venv\Scripts\python scripts\validate_guardian.py
echo.
pause
goto menu

:judge
echo.
set /p subfile="  Path to submission JSON (e.g. my_strategy.json): "
if not exist "%subfile%" (
    echo.
    echo  [!] File not found: %subfile%
    echo.
    pause
    goto menu
)
echo.
venv\Scripts\python scripts\guardian_assess.py "%subfile%"
echo.
echo  (exit 0 = PASS, 2 = FAIL)
echo.
pause
goto menu

:example
echo.
set /p newname="  New submission filename (e.g. my_strategy.json): "
copy docs\research\guardian_example_submission.json "%newname%"
echo.
echo  Created %newname% - open it, fill in your backtest numbers,
echo  then use menu option [2] to judge it.
echo.
pause
goto menu
