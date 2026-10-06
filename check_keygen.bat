@echo off
setlocal
cd /d "%~dp0"

echo ============================================
echo   KEYGEN SELF-CHECK
echo ============================================
echo.

set "PY="
where python >nul 2>&1
if %ERRORLEVEL%==0 set "PY=python"
if not defined PY (
  where py >nul 2>&1
  if %ERRORLEVEL%==0 set "PY=py -3"
)
if not defined PY if exist "%LocalAppData%\Programs\Python\Python314\python.exe" set "PY=%LocalAppData%\Programs\Python\Python314\python.exe"
if not defined PY if exist "%LocalAppData%\Programs\Python\Python312\python.exe" set "PY=%LocalAppData%\Programs\Python\Python312\python.exe"
if not defined PY if exist "%LocalAppData%\Programs\Python\Python311\python.exe" set "PY=%LocalAppData%\Programs\Python\Python311\python.exe"

echo PATH python search:
where python 2>nul
where py 2>nul
echo.

if not defined PY (
  echo [FAIL] No python.exe found.
  echo Result also saved to check_keygen_report.txt
  (
    echo KEYGEN SELF-CHECK
    echo [FAIL] python.exe not found
    echo Fix: install Python, tick Add python.exe to PATH
    echo Close ALL cmd windows and run this file again.
  ) > "%~dp0check_keygen_report.txt"
  goto :end
)

echo Using: %PY%
%PY% --version
echo.
echo Running diag_keygen.py ...
echo.
%PY% "%~dp0diag_keygen.py"
echo.

:end
echo.
echo Report file: check_keygen_report.txt
pause
