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
echo  -- Cache --
echo  Tests with same strategy version will be SKIPPED (cached).
echo  Type F to FORCE re-run all tests, or press Enter to use cache.
set /p forceflag="  Force re-run? (F/Enter) [cache]: "
if /i "%forceflag%"=="F" (set forcearg=--force) else (set forcearg=)
echo.

echo  -- Scope --
echo  [1] ALL strategies x ALL symbols x ALL timeframes (full)
echo  [2] ALL strategies x ALL symbols (H1 only - fast)
echo  [3] SMA Crossover only
echo  [4] MACD Crossover only
echo  [5] RSI Reversal only
echo  [6] Bollinger Bounce only
echo  [7] ML Direct only
echo  [8] ML Filtered SMA only
echo  [9] Specific symbol
echo.
set /p choice="  Choose (1-9): "

if "%choice%"=="1" (
    echo.
    echo  Running FULL backtest [%prof%]...
    echo.
    venv\Scripts\python scripts\run_backtest_all.py --profile %prof% %forcearg%
)
if "%choice%"=="2" (
    echo.
    venv\Scripts\python scripts\run_backtest_all.py --profile %prof% %forcearg% --timeframe H1
)
if "%choice%"=="3" (
    echo.
    venv\Scripts\python scripts\run_backtest_all.py --profile %prof% %forcearg% --strategy sma_crossover
)
if "%choice%"=="4" (
    echo.
    venv\Scripts\python scripts\run_backtest_all.py --profile %prof% %forcearg% --strategy macd_crossover
)
if "%choice%"=="5" (
    echo.
    venv\Scripts\python scripts\run_backtest_all.py --profile %prof% %forcearg% --strategy rsi_reversal
)
if "%choice%"=="6" (
    echo.
    venv\Scripts\python scripts\run_backtest_all.py --profile %prof% %forcearg% --strategy bollinger_bounce
)
if "%choice%"=="7" (
    echo.
    venv\Scripts\python scripts\run_backtest_all.py --profile %prof% %forcearg% --strategy ml_direct
)
if "%choice%"=="8" (
    echo.
    venv\Scripts\python scripts\run_backtest_all.py --profile %prof% %forcearg% --strategy ml_filtered_sma
)
if "%choice%"=="9" (
    set /p sym="  Enter symbol (e.g. EURUSD): "
    echo.
    venv\Scripts\python scripts\run_backtest_all.py --profile %prof% %forcearg% --symbol %sym%
)

echo.
echo  =============================================
echo  Backtest complete! Profile: %prof%
echo.
echo  Results:   data\backtest_results.db
echo  Approved:  data\backtest_approved.yaml
echo  =============================================
echo.
echo  Starting trading system...
echo.
call start.bat
