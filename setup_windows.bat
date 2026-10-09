@echo off
REM One-time setup + start for Windows (cmd). Double-click or run:  setup_windows.bat
python --version >nul 2>&1 || (echo Python 3.10+ is required. Install from python.org and tick "Add to PATH". & pause & exit /b 1)
if not exist venv (python -m venv venv)
call venv\Scripts\activate
python -m pip install --upgrade pip >nul
pip install -r requirements.txt || (echo pip install failed & pause & exit /b 1)
python database\seed.py
echo.
echo Starting NetVote on http://127.0.0.1:5000  (Ctrl+C to stop)
python run.py
