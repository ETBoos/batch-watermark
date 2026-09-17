@echo off
chcp 65001 >nul
cd /d "%~dp0"
set "PATH=%USERPROFILE%\.local\bin;%USERPROFILE%\.cargo\bin;C:\ffmpeg\bin;%PATH%"
title 视频批量图片水印工具
echo 正在启动「视频批量图片水印工具」...
echo 目录: %cd%
echo.

where python >nul 2>&1
if errorlevel 1 (
  echo [错误] 未找到 python。请先安装 Python 3.10+ 并勾选 Add to PATH，
  echo       然后双击运行 安装配置-Windows.bat
  goto :end
)

where uv >nul 2>&1
if errorlevel 1 (
  echo [错误] 未找到 uv，请先双击运行 安装配置-Windows.bat
  goto :end
)

where ffmpeg >nul 2>&1
if errorlevel 1 (
  if exist "C:\ffmpeg\bin\ffmpeg.exe" set "PATH=C:\ffmpeg\bin;%PATH%"
)
where ffmpeg >nul 2>&1
if errorlevel 1 (
  echo [警告] 未找到 ffmpeg，界面可能能开但无法处理视频。
  echo.
)

echo 使用: uv run python -m batch_watermark
echo.
uv run python -m batch_watermark
set "EC=%ERRORLEVEL%"
if not "%EC%"=="0" (
  echo.
  echo ========== 启动失败 code=%EC% ==========
  echo 请依次尝试:
  echo   1. 双击 安装配置-Windows.bat
  echo   2. 新开 CMD 再运行本脚本
  echo   3. 把上面的红色报错发给开发者
  echo.
)

:end
echo.
pause
