@echo off
chcp 65001 >nul
cd /d "%~dp0"
set "PATH=%USERPROFILE%\.local\bin;%USERPROFILE%\.cargo\bin;C:\ffmpeg\bin;%PATH%"
title batch-watermark
echo Starting batch-watermark ...
echo Folder: %cd%
echo.

where python >nul 2>&1
if errorlevel 1 (
  echo [ERROR] python not found. Install Python 3.10+ with Add to PATH,
  echo         then run setup-win.ps1
  goto end
)

where uv >nul 2>&1
if errorlevel 1 (
  echo [ERROR] uv not found. Run setup-win.ps1 first.
  goto end
)

where ffmpeg >nul 2>&1
if errorlevel 1 (
  if exist "C:\ffmpeg\bin\ffmpeg.exe" set "PATH=C:\ffmpeg\bin;%PATH%"
)
where ffmpeg >nul 2>&1
if errorlevel 1 (
  echo [WARN] ffmpeg not found. GUI may open but video processing will fail.
  echo.
)

echo Running: uv run python -m batch_watermark
echo.
uv run python -m batch_watermark
set "EC=%ERRORLEVEL%"
if not "%EC%"=="0" (
  echo.
  echo ========== START FAILED code=%EC% ==========
  echo 1. Run: powershell -ExecutionPolicy Bypass -File setup-win.ps1
  echo 2. Open a NEW window and retry
  echo 3. Copy the error text above
  echo.
)

:end
echo.
pause
