@echo off
cd /d %~dp0
python -m pip install -r requirements.txt
python -m playwright install chromium
echo.
echo Now log in to each account:
python claimer.py login acc1
python claimer.py login acc2
python claimer.py login acc3
pause
