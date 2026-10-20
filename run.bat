@echo off
REM Launcher for Offline AI 3D Designer
cd /d "%~dp0"
call .venv\Scripts\activate.bat
python run_gui.py
pause
