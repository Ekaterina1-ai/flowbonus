@echo off
cd /d "%~dp0"
echo Installing dependencies...
python -m pip install -r requirements.txt
echo.
echo Starting FlowBonus on http://127.0.0.1:5500
python app.py
