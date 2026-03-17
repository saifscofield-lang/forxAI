@echo off
:: Run this as Administrator to set up auto-start for paper trading
schtasks /create /tn "ForexAI_PaperTrade" /tr "D:\forexAI\scripts\start_paper_trade.bat" /sc onlogon /rl highest /f
if %errorlevel%==0 (
    echo SUCCESS: ForexAI_PaperTrade task created!
    echo Paper trading will auto-start when you log in to Windows.
    echo.
    echo To check:   schtasks /query /tn "ForexAI_PaperTrade"
    echo To remove:  schtasks /delete /tn "ForexAI_PaperTrade" /f
) else (
    echo FAILED: Please run this script as Administrator
    echo Right-click the .bat file and select "Run as administrator"
)
pause
