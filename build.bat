@echo off
setlocal
cd /d "%~dp0"

call "%~dp0_find_python.bat"
if errorlevel 1 (
  pause
  exit /b 1
)

echo ============================================
echo   Build PDF Tool  -  by TingFei
echo ============================================
%PY% --version
echo.

if not exist "%~dp0pdf2word.py" (
  echo [ERROR] pdf2word.py not found here.
  pause
  exit /b 1
)
if not exist "%~dp0pdf2word_gui.py" (
  echo [ERROR] pdf2word_gui.py not found here.
  pause
  exit /b 1
)
if not exist "%~dp0license_core.py" (
  echo [ERROR] license_core.py not found here.
  pause
  exit /b 1
)

echo [1/2] Installing tools and libraries (first time only)...
%PY% -m pip install pyinstaller customtkinter cryptography pymupdf python-docx pdf2docx pillow
echo.

set "ICONARG="
if exist "%~dp0icon_64.ico" set ICONARG=--icon="%~dp0icon_64.ico"

echo [2/2] Building the app ... this can take several minutes.
echo.
%PY% -m PyInstaller --onefile --windowed --noconfirm --clean --name "PDF2Word" ^
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
if exist "%~dp0dist\PDF2Word.exe" (
  echo SUCCESS !  ->  %~dp0dist\PDF2Word.exe
  echo The exe now uses icon_64.ico as its icon.
) else (
  echo Build did not produce the exe. Please send me the messages above.
)
echo ============================================
pause
