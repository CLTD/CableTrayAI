@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
echo.
echo ============================================================
echo CableTrayAI installer
echo This will copy CableTrayAI to a selected local folder and
echo create a desktop shortcut.
echo ============================================================
echo.
if exist "%~dp0CableTrayAI_Installer.exe" (
  start "" /wait "%~dp0CableTrayAI_Installer.exe"
) else (
  powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\install_desktop_app.ps1"
)
if errorlevel 1 (
  echo.
  echo Installation failed. Please send logs\install_desktop_app.log to admin-duxyb.
  pause
  exit /b 1
)
echo.
echo Installation completed. Use the CableTrayAI desktop shortcut.
pause
