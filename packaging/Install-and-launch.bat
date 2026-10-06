@echo off
setlocal
set "GEARFORGE_KIT_DIR=%~dp0"
set /p GEARFORGE_VERSION=<"%GEARFORGE_KIT_DIR%VERSION.txt"
set "GEARFORGE_ENV_DIR=%LOCALAPPDATA%\GearForgeStudio\venv-%GEARFORGE_VERSION%"
where py >nul 2>nul
if errorlevel 1 (
  echo Install 64-bit Python 3.11, 3.12 or 3.13 from python.org, then run again.
  pause
  exit /b 1
)
py -3 -c "import sys; assert (3,11) <= sys.version_info[:2] < (3,14), 'Python 3.11-3.13 is required'"
if errorlevel 1 (pause & exit /b 1)
if not exist "%GEARFORGE_ENV_DIR%\Scripts\python.exe" py -3 -m venv "%GEARFORGE_ENV_DIR%"
if errorlevel 1 (pause & exit /b 1)
"%GEARFORGE_ENV_DIR%\Scripts\python.exe" -m pip show gearforge-studio >nul 2>nul
if errorlevel 1 (
  "%GEARFORGE_ENV_DIR%\Scripts\python.exe" -m pip install -c "%GEARFORGE_KIT_DIR%constraints-release.txt" "%GEARFORGE_KIT_DIR%dist\gearforge_studio-%GEARFORGE_VERSION%-py3-none-any.whl"
  if errorlevel 1 (pause & exit /b 1)
)
"%GEARFORGE_ENV_DIR%\Scripts\python.exe" -m gearforge gui
if errorlevel 1 pause
