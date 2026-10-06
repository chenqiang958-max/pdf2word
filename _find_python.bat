@echo off
rem ??? bat ???call "%~dp0_find_python.bat"
rem ????? PY=??? python ????

set "PY="

py -3.12 -c "import sys" >nul 2>&1
if not errorlevel 1 (
  set "PY=py -3.12"
  goto :ok
)
py -3 -c "import sys" >nul 2>&1
if not errorlevel 1 (
  set "PY=py -3"
  goto :ok
)
python -c "import sys" >nul 2>&1
if not errorlevel 1 (
  set "PY=python"
  goto :ok
)
python3 -c "import sys" >nul 2>&1
if not errorlevel 1 (
  set "PY=python3"
  goto :ok
)

if exist "%LocalAppData%\Programs\Python\Python312\python.exe" (
  set "PY=%LocalAppData%\Programs\Python\Python312\python.exe"
  goto :ok
)
if exist "%LocalAppData%\Programs\Python\Python311\python.exe" (
  set "PY=%LocalAppData%\Programs\Python\Python311\python.exe"
  goto :ok
)
if exist "%ProgramFiles%\Python312\python.exe" (
  set "PY=%ProgramFiles%\Python312\python.exe"
  goto :ok
)
if exist "%ProgramFiles%\Python311\python.exe" (
  set "PY=%ProgramFiles%\Python311\python.exe"
  goto :ok
)
if exist "%LocalAppData%\Microsoft\WindowsApps\python3.12.exe" (
  set "PY=%LocalAppData%\Microsoft\WindowsApps\python3.12.exe"
  goto :ok
)
if exist "%LocalAppData%\Microsoft\WindowsApps\python.exe" (
  set "PY=%LocalAppData%\Microsoft\WindowsApps\python.exe"
  goto :ok
)

echo.
echo [??] ????? Python?
echo.
echo ???? "'py' ?????????" ???????
echo Windows ???? Python ??? py.exe?
echo.
echo ????????
echo   1. ?? https://www.python.org/downloads/ ?? Python 3.12
echo      ??????? "Add python.exe to PATH"
echo   2. ?????????? Python????
echo      ?? ? ?? ? ?????? ? ??????
echo      ?? "python.exe" ? "python3.exe"
echo.
exit /b 1

:ok
exit /b 0
