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

rem Start clean so no file from an older build is left in the output.
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

%VPY% -m pip install --upgrade pip || goto :fail
rem pywebview / pythonnet are no longer used; remove them if an older build installed them.
%VPY% -m pip uninstall -y pywebview pythonnet clr_loader >nul 2>&1
%VPY% -m pip install -r requirements.txt pyinstaller || goto :fail
%VPY% -m PyInstaller --noconfirm --clean ISWM.spec || goto :fail

for /f %%v in ('%VPY% -c "import iswm; print(iswm.__version__)"') do set "VER=%%v"
echo.
echo Done. Built ISWM version %VER% in dist\ISWM\ISWM.exe
echo Copy the WHOLE dist\ISWM folder to the other PC, after deleting the old ISWM folder there.
pause
exit /b 0

:fail
echo.
echo Build failed. Copy the messages above and send them.
echo To start clean, delete the .venv folder and run this again.
pause
exit /b 1
