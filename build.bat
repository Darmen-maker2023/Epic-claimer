@echo off
setlocal
cd /d "%~dp0" || exit /b 1

echo Installing dependencies...
python -m pip install -r requirements.txt pyinstaller
if errorlevel 1 goto :failed

echo Building EpicClaimer.exe...
python -m PyInstaller --noconfirm --onefile --windowed --name EpicClaimer ^
  --clean ^
  --add-data "config.json;." ^
  --collect-all playwright ^
  --collect-all customtkinter ^
  --collect-all aiohttp ^
  --hidden-import claimer ^
  gui.py
if errorlevel 1 goto :failed

if not exist "dist\EpicClaimer.exe" goto :failed
if exist dist\EpicClaimer.exe copy /Y dist\EpicClaimer.exe EpicClaimer.exe >nul
if errorlevel 1 goto :failed

echo Build succeeded: %~dp0EpicClaimer.exe
exit /b 0

:failed
echo BUILD FAILED. EpicClaimer.exe was not updated.
exit /b 1
