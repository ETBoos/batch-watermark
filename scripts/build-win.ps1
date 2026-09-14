# Windows PyInstaller build script for 批量水印工具
# Prerequisites: Windows, Python 3.10+, uv installed, run from repo root.
# Usage:  .\scripts\build-win.ps1

$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

Write-Host "==> uv sync" -ForegroundColor Cyan
uv sync --group dev

Write-Host "==> install PyInstaller" -ForegroundColor Cyan
uv pip install pyinstaller

$entry = "src/batch_watermark/__main__.py"
$name = "批量水印工具"

Write-Host "==> PyInstaller onefile/onedir build" -ForegroundColor Cyan
uv run pyinstaller `
  --noconfirm `
  --clean `
  --windowed `
  --name $name `
  --paths src `
  --collect-all PySide6 `
  --collect-all PIL `
  --hidden-import batch_watermark `
  --hidden-import batch_watermark.gui.main_window `
  --hidden-import batch_watermark.engines.image_engine `
  --hidden-import batch_watermark.engines.video_engine `
  $entry

Write-Host ""
Write-Host "Build finished. Output under .\dist\$name\" -ForegroundColor Green
Write-Host "Reminder: ship ffmpeg.exe separately or instruct users to install ffmpeg on PATH." -ForegroundColor Yellow
Write-Host "Common paths: C:\ffmpeg\bin\ffmpeg.exe , winget install ffmpeg" -ForegroundColor Yellow
