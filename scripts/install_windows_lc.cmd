@echo off
setlocal

set "PYTHON=D:\SoftService\miniconda3\envs\lc\python.exe"
set "PROJECT=D:\PythonProject\builder\image-translator-poc"

if not exist "%PYTHON%" (
  echo Python was not found: %PYTHON%
  exit /b 1
)

net session >nul 2>&1
if errorlevel 1 (
  echo This environment is administrator-owned. Run this script from an Administrator terminal.
  exit /b 2
)

cd /d "%PROJECT%"
"%PYTHON%" -m pip install --no-user -r requirements-windows-lc.txt
if errorlevel 1 exit /b %errorlevel%

echo.
echo The existing PyTorch installation still needs repair.
echo For CPU validation run:
echo   "%PYTHON%" -m pip install --no-user --force-reinstall torch==2.8.0 --index-url https://download.pytorch.org/whl/cpu
echo.
echo For a CUDA host, choose the wheel command from https://pytorch.org/get-started/locally/
echo that matches the installed NVIDIA driver. Do not guess the CUDA index URL.

endlocal

