@echo off
setlocal enabledelayedexpansion
title Batch Folder Hindi Dubber

echo ===============================================================================
echo                 BATCH FOLDER HINDI VIDEO DUBBER
echo ===============================================================================
echo.

set "TARGET_DIR=%~1"
if "%TARGET_DIR%"=="" set "TARGET_DIR=%~dp0"

echo Scanning for videos in: "%TARGET_DIR%"
echo.

for %%F in ("%TARGET_DIR%\*.mkv" "%TARGET_DIR%\*.mp4" "%TARGET_DIR%\*.avi") do (
    set "FNAME=%%~nF"
    :: Skip files already dubbed
    echo !FNAME! | findstr /i "_hindi" >nul
    if errorlevel 1 (
        echo [PROCESSING] "%%~nxF"...
        python "%~dp0auto_dubber.py" "%%~fF"
        echo -------------------------------------------------------------------------------
    ) else (
        echo [SKIPPING] Already dubbed: "%%~nxF"
    )
)

echo.
echo ===============================================================================
echo  All videos in folder have been processed!
echo ===============================================================================
echo.
pause
