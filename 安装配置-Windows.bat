@echo off
chcp 65001 >nul
setlocal EnableExtensions EnableDelayedExpansion
title 视频批量图片水印工具 - Windows 安装配置
cd /d "%~dp0"

echo.
echo ========================================
echo   视频批量图片水印工具 - Windows 安装配置
echo ========================================
echo   仓库目录: %cd%
echo.

REM ---------- helpers ----------
set "ERR=0"

echo [1/6] 检查 Python ...
where python >nul 2>&1
if errorlevel 1 (
  echo   [失败] 未找到 python。
  echo   请安装 Python 3.10+ ：https://www.python.org/downloads/windows/
  echo   安装时务必勾选 "Add python.exe to PATH"，然后重新运行本脚本。
  set "ERR=1"
  goto :summary
)
for /f "tokens=*" %%V in ('python --version 2^>^&1') do set "PYVER=%%V"
echo   [OK] !PYVER!

echo.
echo [2/6] 检查 / 安装 uv ...
where uv >nul 2>&1
if errorlevel 1 (
  echo   未找到 uv，正在安装...
  powershell -NoProfile -ExecutionPolicy Bypass -Command "irm https://astral.sh/uv/install.ps1 | iex"
  if errorlevel 1 (
    echo   [失败] uv 安装失败，请手动执行:
    echo   powershell -ExecutionPolicy Bypass -Command "irm https://astral.sh/uv/install.ps1 | iex"
    set "ERR=1"
    goto :summary
  )
  REM refresh PATH for current session (common uv install locations)
  set "PATH=%USERPROFILE%\.local\bin;%USERPROFILE%\.cargo\bin;%PATH%"
)
where uv >nul 2>&1
if errorlevel 1 (
  echo   [失败] 仍未找到 uv。请关闭窗口后重新打开，或把 uv 所在目录加入 PATH。
  echo   常见路径: %USERPROFILE%\.local\bin
  set "ERR=1"
  goto :summary
)
for /f "tokens=*" %%V in ('uv --version 2^>^&1') do set "UVVER=%%V"
echo   [OK] !UVVER!

echo.
echo [3/6] 检查 / 安装 ffmpeg ...
where ffmpeg >nul 2>&1
if errorlevel 1 (
  if exist "C:\ffmpeg\bin\ffmpeg.exe" (
    set "PATH=C:\ffmpeg\bin;%PATH%"
  )
)
where ffmpeg >nul 2>&1
if errorlevel 1 (
  echo   未找到 ffmpeg，尝试用 winget 安装...
  where winget >nul 2>&1
  if errorlevel 1 (
    echo   [警告] 没有 winget。请手动安装 ffmpeg:
    echo   https://www.gyan.dev/ffmpeg/builds/
    echo   解压后把 bin 目录加入 PATH，或放到 C:\ffmpeg\bin\
    set "ERR=1"
  ) else (
    winget install --id Gyan.FFmpeg -e --accept-package-agreements --accept-source-agreements
    if errorlevel 1 (
      echo   [警告] winget 安装 ffmpeg 失败，请手动安装后重试。
      set "ERR=1"
    ) else (
      echo   [OK] winget 已安装 ffmpeg。若仍提示找不到，请新开一个 CMD 再运行「启动-Windows.bat」。
    )
  )
) else (
  for /f "tokens=*" %%V in ('ffmpeg -version 2^>^&1') do (
    echo   [OK] %%V
    goto :ffmpeg_ok
  )
)
:ffmpeg_ok
where ffmpeg >nul 2>&1
if not errorlevel 1 (
  echo   检查 H.264 编码器...
  ffmpeg -hide_banner -encoders 2>nul | findstr /i "libx264 h264_nvenc h264_amf h264_qsv"
)

echo.
echo [4/6] 安装项目依赖 ^(uv sync^) ...
if not exist "pyproject.toml" (
  echo   [失败] 当前目录没有 pyproject.toml，请把本 bat 放在仓库根目录运行。
  set "ERR=1"
  goto :summary
)
uv sync
if errorlevel 1 (
  echo   [失败] uv sync 失败。
  set "ERR=1"
  goto :summary
)
echo   [OK] 依赖安装完成

echo.
echo [5/6] 写入启动脚本 ...
echo   保留仓库自带的 启动-Windows.bat（不再覆盖，避免闪退看不到报错）
echo   [OK] 已生成 启动-Windows.bat

echo.
echo [6/6] 环境自检摘要 ...
echo   Python : 
python --version 2>&1
echo   uv     : 
uv --version 2>&1
echo   ffmpeg : 
where ffmpeg 2>&1
ffmpeg -version 2>&1 | more +0 | findstr /i "ffmpeg version"
echo   显卡   :
powershell -NoProfile -Command "Get-CimInstance Win32_VideoController | Select-Object -ExpandProperty Name"

:summary
echo.
echo ========================================
if "%ERR%"=="0" (
  echo   配置完成。
  echo   以后双击: 启动-Windows.bat
  echo   或本窗口输入 Y 立即启动。
  echo ========================================
  set /p GO=现在启动图形界面吗？(Y/N): 
  if /i "!GO!"=="Y" (
    uv run python -m batch_watermark
  )
) else (
  echo   配置未完全成功，请根据上面的红色/失败提示处理后再运行本脚本。
  echo ========================================
)
echo.
pause
endlocal
