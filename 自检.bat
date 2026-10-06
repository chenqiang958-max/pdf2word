@echo off
chcp 65001 >nul
cd /d "%~dp0"
call "%~dp0_find_python.bat"
if errorlevel 1 (
  pause
  exit /b 1
)
echo Running self-check...
%PY% "%~dp0selfcheck.py"
pause
