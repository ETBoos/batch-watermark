@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
title 环境自检
set "PATH=%USERPROFILE%\.local\bin;%USERPROFILE%\.cargo\bin;C:\ffmpeg\bin;%PATH%"
echo === 视频批量图片水印 - 环境自检 ===
echo.
echo [Python]
where python 2>&1
python --version 2>&1
echo.
echo [uv]
where uv 2>&1
uv --version 2>&1
echo.
echo [ffmpeg]
where ffmpeg 2>&1
ffmpeg -version 2>&1 | findstr /i "version"
echo.
echo [H.264 encoders]
ffmpeg -hide_banner -encoders 2>nul | findstr /i "libx264 h264_nvenc h264_amf h264_qsv"
echo.
echo [GPU]
powershell -NoProfile -Command "Get-CimInstance Win32_VideoController | Format-Table Name,DriverVersion -AutoSize"
echo.
echo [Project]
if exist "pyproject.toml" (echo pyproject.toml: OK) else (echo pyproject.toml: MISSING)
echo.
pause
endlocal
