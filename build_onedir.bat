@echo off
setlocal
cd /d "%~dp0"

set "PY=py -3.12"
%PY% --version >nul 2>&1
if errorlevel 1 set "PY=python"

echo ============================================
echo   Build PDF Tool (FOLDER mode, AV-friendly)
echo ============================================
%PY% --version
echo.

if not exist "%~dp0pdf2word_gui.py" (
  echo [ERROR] pdf2word_gui.py not found here.
  pause
  exit /b 1
)

echo [1/2] Installing tools and libraries (first time only)...
%PY% -m pip install pyinstaller customtkinter cryptography pymupdf python-docx pdf2docx pillow
echo.

set "ICONARG="
if exist "%~dp0icon_64.ico" set ICONARG=--icon="%~dp0icon_64.ico"

echo [2/2] Building (folder mode) ... this can take several minutes.
echo.
%PY% -m PyInstaller --onedir --windowed --noconfirm --clean --name "PDF2Word" ^
  %ICONARG% ^
  --collect-all pdf2docx ^
  --collect-all pymupdf ^
  --collect-all fontTools ^
  --collect-all customtkinter ^
  --collect-all cryptography ^
  --hidden-import pdf2word ^
  --hidden-import license_core ^
  pdf2word_gui.py

echo.
echo ============================================
if exist "%~dp0dist\PDF2Word\PDF2Word.exe" (
  echo SUCCESS !
  echo Your program folder is here:  %~dp0dist\PDF2Word\
  echo Run it by:  dist\PDF2Word\PDF2Word.exe
  echo Give customers the WHOLE dist\PDF2Word folder,
  echo or make an installer with Inno Setup (see note).
) else (
  echo Build did not produce the exe. Please send me the messages above.
)
echo ============================================
pause
