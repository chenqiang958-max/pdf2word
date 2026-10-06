@echo off
setlocal
cd /d "%~dp0"

rem ===== 注册机打包脚本（只给你自己用，切勿分发！）=====
call "%~dp0_find_python.bat"
if errorlevel 1 (
  pause
  exit /b 1
)

echo ============================================
echo   Build KEYGEN (SELLER ONLY - do NOT ship)
echo ============================================
%PY% --version
echo.

if not exist "%~dp0keygen.py" (
  echo [ERROR] keygen.py not found here.
  pause
  exit /b 1
)

echo Installing tools...
%PY% -m pip install pyinstaller customtkinter cryptography
echo.

echo Building keygen.exe ...
%PY% -m PyInstaller --onefile --windowed --noconfirm --clean --name "keygen" ^
  --collect-all customtkinter ^
  --collect-all cryptography ^
  keygen.py

echo.
echo ============================================
if exist "%~dp0dist\keygen.exe" (
  echo SUCCESS ! -> %~dp0dist\keygen.exe
  echo.
  echo IMPORTANT: put private_key.hex in the SAME folder as keygen.exe
  echo Keep keygen.exe + private_key.hex on YOUR machine only.
) else (
  echo Build failed. Send me the messages above.
)
echo ============================================
pause
