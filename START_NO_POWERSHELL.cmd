@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
if exist "runtime\CableTrayAI_Server\CableTrayAI_Server.exe" (
  start "" "runtime\CableTrayAI_Server\CableTrayAI_Server.exe" --root "%~dp0" --host 0.0.0.0 --port 8000
  timeout /t 6 /nobreak >nul
  start "" "http://127.0.0.1:8000/"
) else (
  echo Missing runtime\CableTrayAI_Server\CableTrayAI_Server.exe
  echo Use START_CABLETRAYAI.cmd for PowerShell startup.
)
pause
