@echo off
rem Build ISWM.exe inside a virtual environment (.venv) in this folder.
rem Double-click this file, or run it from this folder.
cd /d "%~dp0"

rem Prefer Python 3.12 through the py launcher if it is installed; otherwise use "python".
set "PY=python"
py -3.12 --version >nul 2>&1 && set "PY=py -3.12"

if not exist ".venv\Scripts\python.exe" (
  echo Creating virtual environment with: %PY%
  %PY% -m venv .venv || goto :fail
)
set "VPY=.venv\Scripts\python.exe"
%VPY% --version

%VPY% -m pip install --upgrade pip || goto :fail
%VPY% -m pip install -r requirements.txt pyinstaller || goto :fail
%VPY% -m PyInstaller --noconfirm ISWM.spec || goto :fail

echo.
echo Done. The app is in dist\ISWM\ISWM.exe
pause
exit /b 0

:fail
echo.
echo Build failed. Copy the messages above and send them.
echo To start clean, delete the .venv folder and run this again.
pause
exit /b 1
