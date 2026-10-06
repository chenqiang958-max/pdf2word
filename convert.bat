@echo off
setlocal
cd /d "%~dp0"
set "LOG=%~dp0convert_log.txt"

rem Use Python 3.12 (needed for editable mode); fall back to default python
set "PY=py -3.12"
%PY% --version >nul 2>&1
if errorlevel 1 set "PY=python"

echo ============================================
echo   PDF to Word Converter
echo ============================================
echo.
echo Folder: %~dp0
%PY% --version
echo.

if not exist "%~dp0pdf2word.py" (
  echo [ERROR] pdf2word.py was NOT found in this folder.
  echo Put convert.bat and pdf2word.py together, then run again.
  echo.
  echo Press any key to close ...
  pause >nul
  exit /b 1
)

echo ==== run %date% %time% ==== > "%LOG%"
%PY% --version >> "%LOG%" 2>&1

set /a count=0
set /a fail=0
for %%F in ("%~dp0*.pdf") do (
  set /a count+=1
  echo [%%~nxF] converting ...
  echo ---- %%~nxF ---- >> "%LOG%"
  %PY% "%~dp0pdf2word.py" "%%~fF" >> "%LOG%" 2>&1
  if errorlevel 1 (
    echo    ^> FAILED
    set /a fail+=1
  ) else (
    echo    ^> done
  )
)

echo.
echo --------------------------------------------
if "%count%"=="0" (
  echo No PDF file found in this folder.
  echo Copy your PDF into this folder, then run convert.bat again.
) else (
  echo Finished. Total PDF: %count%   Failed: %fail%
  echo The Word files are in this same folder.
)
echo --------------------------------------------
echo Details were written to convert_log.txt
echo.

powershell -NoProfile -Command "Add-Type -AssemblyName System.Windows.Forms; [System.Windows.Forms.MessageBox]::Show('Finished. Total: %count%  Failed: %fail%.  Word files are saved in the same folder as your PDF.', 'PDF to Word - Completed') | Out-Null" 2>nul

echo Press any key to close ...
pause >nul
endlocal
