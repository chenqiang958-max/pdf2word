@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

echo ============================================
echo   启动 PDF 工具（源码调试）
echo ============================================
echo.

call "%~dp0_find_python.bat"
if errorlevel 1 (
  pause
  exit /b 1
)

echo 使用的 Python：%PY%
%PY% --version
echo.

echo [1/2] 检查依赖...
%PY% -m pip install customtkinter cryptography pymupdf python-docx pdf2docx pillow
echo.
echo [2/2] 启动软件...
%PY% pdf2word_gui.py
echo.
echo 若没有弹出窗口，请把上面的红色文字截图保存。
pause
