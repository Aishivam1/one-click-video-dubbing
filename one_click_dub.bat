@echo off
setlocal enabledelayedexpansion
title 1-Click English to Hindi Video Dubber

echo ===============================================================================
echo            1-CLICK AUTOMATIC ENGLISH TO HINDI VIDEO DUBBER
echo ===============================================================================
echo.

:: Check Python installation
python --version >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Python is not installed or not in your system PATH!
    echo Please install Python 3.9+ from https://www.python.org/
    echo.
    pause
    exit /b 1
)

:: Check FFmpeg installation
ffmpeg -version >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] FFmpeg is not installed or not in your system PATH!
    echo Please install FFmpeg to run the dubbing pipeline.
    echo.
    pause
    exit /b 1
)

:: Get target video path (from drag-and-drop or prompt)
set "VIDEO_PATH=%~1"

if "%VIDEO_PATH%"=="" (
    echo [INFO] No file was dragged onto the script.
    echo Opening file selector dialog...
    python "%~dp0auto_dubber.py"
) else (
    echo [INFO] Video received: "%VIDEO_PATH%"
    python "%~dp0auto_dubber.py" "%VIDEO_PATH%"
)

echo.
echo ===============================================================================
echo  Dubbing process completed!
echo ===============================================================================
echo.
pause
