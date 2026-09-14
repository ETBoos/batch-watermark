@echo off
chcp 65001 >nul
cd /d "%~dp0"
set "PATH=%USERPROFILE%\.local\bin;%USERPROFILE%\.cargo\bin;C:\ffmpeg\bin;%PATH%"
title 视频批量图片水印工具
echo 正在启动「视频批量图片水印工具」...
echo 若首次使用，请先运行 安装配置-Windows.bat
echo.
where uv >nul 2>&1
if errorlevel 1 (
  echo [错误] 未找到 uv，请先运行 安装配置-Windows.bat
  pause
  exit /b 1
)
where ffmpeg >nul 2>&1
if errorlevel 1 (
  if exist "C:\ffmpeg\bin\ffmpeg.exe" set "PATH=C:\ffmpeg\bin;%PATH%"
)
where ffmpeg >nul 2>&1
if errorlevel 1 (
  echo [警告] 未找到 ffmpeg，窗口可能无法处理视频。请先运行 安装配置-Windows.bat
  echo.
)
uv run python -m batch_watermark
if errorlevel 1 (
  echo.
  echo 启动失败。请先运行 安装配置-Windows.bat 完成环境配置。
  pause
)
