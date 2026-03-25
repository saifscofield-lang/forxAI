@echo off
echo Training Market Learner models...
cd /d D:\forexAI
call venv\Scripts\activate
python ml/market_learner.py %*
echo.
echo Done! Models saved in models/market_learner/
pause
