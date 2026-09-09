@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Please follow START_HERE.txt to create .venv first.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" panel.py
pause
