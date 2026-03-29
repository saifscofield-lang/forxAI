@echo off
title ForexAI Backtest
color 0E
cd /d d:\forexAI

echo.
echo  =============================================
echo       ForexAI Universal Backtest
echo  =============================================
echo.
echo  -- Risk Profile --
echo  [S] Strict    (PF^>1.3  DD^<8%%  WR^>45%%  Sharpe^>0.5  Trades^>50)
echo  [M] Moderate  (PF^>1.15 DD^<10%% WR^>40%%  Sharpe^>0.3  Trades^>30)  [default]
echo  [A] Aggressive(PF^>1.05 DD^<15%% WR^>35%%  Sharpe^>0    Trades^>15)
echo.
set /p profile="  Profile (S/M/A) [M]: "
if /i "%profile%"=="S" (set prof=strict) else if /i "%profile%"=="A" (set prof=aggressive) else (set prof=moderate)
echo.
echo  Selected: %prof%
echo.

echo  -- Scope --
echo  [1] ALL strategies x ALL symbols x ALL timeframes (full)
echo  [2] ALL strategies x ALL symbols (H1 only - fast)
echo  [3] MACD Crossover only
echo  [4] RSI Reversal only
echo  [5] Bollinger Bounce only
echo  [6] Specific symbol
echo.
set /p choice="  Choose (1-6): "

if "%choice%"=="1" (
    echo.
    echo  Running FULL backtest [%prof%]...
    echo.
    venv\Scripts\python scripts\run_backtest_all.py --profile %prof%
)
if "%choice%"=="2" (
    echo.
    venv\Scripts\python scripts\run_backtest_all.py --profile %prof% --timeframe H1
)
if "%choice%"=="3" (
    echo.
    venv\Scripts\python scripts\run_backtest_all.py --profile %prof% --strategy macd_crossover
)
if "%choice%"=="4" (
    echo.
    venv\Scripts\python scripts\run_backtest_all.py --profile %prof% --strategy rsi_reversal
)
if "%choice%"=="5" (
    echo.
    venv\Scripts\python scripts\run_backtest_all.py --profile %prof% --strategy bollinger_bounce
)
if "%choice%"=="6" (
    set /p sym="  Enter symbol (e.g. EURUSD): "
    echo.
    venv\Scripts\python scripts\run_backtest_all.py --profile %prof% --symbol %sym%
)

echo.
echo  =============================================
echo  Backtest complete! Profile: %prof%
echo.
echo  Results:   data\backtest_results.db
echo  Approved:  data\backtest_approved.yaml
echo.
echo  Now run start.bat - only approved strategies
echo  will be enabled.
echo  =============================================
echo.
pause
