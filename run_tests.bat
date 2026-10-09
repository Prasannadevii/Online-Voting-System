@echo off
call venv\Scripts\activate
python -m unittest discover -s tests -t . -v
pause
