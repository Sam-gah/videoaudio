@echo off
cd /d "%~dp0"
echo This installs the matching libraries and Windows FFmpeg into this folder.
echo Python 3.10 or later and an internet connection are required for setup only.
where py >nul 2>nul
if %errorlevel% equ 0 (
  py -3 -m pip install --target vendor -r requirements.txt
) else (
  python -m pip install --target vendor -r requirements.txt
)
if errorlevel 1 (
  echo Setup failed. Install Python with pip, then try again. See README.md.
) else (
  echo Setup complete. Double-click Start_Windows.bat to open Editor Desk.
)
pause
