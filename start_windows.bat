@echo off
chcp 65001 >nul
title Photomosaic Studio
cd /d "%~dp0"

echo ============================================================
echo   Photomosaic Studio Launcher
echo ============================================================
echo.

where python >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
    where py >nul 2>nul
    if %ERRORLEVEL% NEQ 0 (
        echo [ERROR] Python was not found on your computer.
        echo Please download and install Python from: https://www.python.org/downloads/
        echo (Make sure to check "Add Python to PATH" during installation).
        echo.
        pause
        exit /b 1
    ) else (
        set PY_CMD=py
    )
) else (
    set PY_CMD=python
)

echo Checking dependencies...
%PY_CMD% -c "import PIL, numpy, tqdm" >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo Installing dependencies (Pillow, NumPy, tqdm)... This is only required on first launch.
    %PY_CMD% -m pip install --quiet pillow numpy tqdm
)

echo Starting Photomosaic Studio...
%PY_CMD% app.py
pause
