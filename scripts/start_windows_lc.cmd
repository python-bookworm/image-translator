@echo off
setlocal

set "PYTHON=D:\SoftService\miniconda3\envs\lc\python.exe"
set "PROJECT=D:\PythonProject\builder\image-translator-poc"

if not exist "%PYTHON%" (
  echo Python was not found: %PYTHON%
  exit /b 1
)

cd /d "%PROJECT%"
"%PYTHON%" scripts\diagnose_environment.py
if errorlevel 1 (
  echo.
  echo Environment readiness check failed. The API was not started.
  exit /b 2
)

"%PYTHON%" run.py
endlocal

