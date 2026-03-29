@echo off
title ForexAI Backtest
color 0E
cd /d d:\forexAI

echo.
echo  =============================================
echo       ForexAI Universal Backtest
echo  =============================================
echo.
echo  [1] ALL strategies x ALL symbols x ALL timeframes (full)
echo  [2] ALL strategies x ALL symbols (H1 only - fast)
echo  [3] MACD Crossover only
echo  [4] RSI Reversal only
echo  [5] Bollinger Bounce only
echo  [6] Specific symbol (will ask)
echo.
set /p choice="  Choose (1-6): "

if "%choice%"=="1" (
    echo.
    echo  Running FULL backtest (all timeframes)...
    echo  This may take 10-20 minutes.
    echo.
    venv\Scripts\python scripts\run_backtest_all.py
)
if "%choice%"=="2" (
    echo.
    echo  Running H1 backtest...
    echo.
    venv\Scripts\python scripts\run_backtest_all.py --timeframe H1
)
if "%choice%"=="3" (
    echo.
    venv\Scripts\python scripts\run_backtest_all.py --strategy macd_crossover
)
if "%choice%"=="4" (
    echo.
    venv\Scripts\python scripts\run_backtest_all.py --strategy rsi_reversal
)
if "%choice%"=="5" (
    echo.
    venv\Scripts\python scripts\run_backtest_all.py --strategy bollinger_bounce
)
if "%choice%"=="6" (
    set /p sym="  Enter symbol (e.g. EURUSD): "
    echo.
    venv\Scripts\python scripts\run_backtest_all.py --symbol %sym%
)

echo.
echo  =============================================
echo  Backtest complete!
echo.
echo  Results:   data\backtest_results.db
echo  Approved:  data\backtest_approved.yaml
echo.
echo  Now run start.bat - it will only enable
echo  strategies that PASSED the backtest.
echo  =============================================
echo.
pause
