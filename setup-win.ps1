# setup-win.ps1 — ASCII-safe Windows setup for batch-watermark
$ErrorActionPreference = "Continue"
Set-Location -LiteralPath $PSScriptRoot
Write-Host "=== batch-watermark Windows setup ==="
Write-Host "Folder: $(Get-Location)"

function Need([string]$name) {
  return -not [bool](Get-Command $name -ErrorAction SilentlyContinue)
}

if (Need "python") {
  Write-Host "[ERROR] python not found. Install from https://www.python.org/downloads/windows/ (tick Add to PATH)"
  Read-Host "Press Enter to exit"
  exit 1
}
Write-Host "[OK] $(python --version)"

$env:Path = "$env:USERPROFILE\.local\bin;$env:USERPROFILE\.cargo\bin;C:\ffmpeg\bin;" + [Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [Environment]::GetEnvironmentVariable("Path","User")

if (Need "uv") {
  Write-Host "Installing uv ..."
  try {
    irm https://astral.sh/uv/install.ps1 | iex
  } catch {
    Write-Host "[ERROR] uv install failed: $_"
    Read-Host "Press Enter to exit"
    exit 1
  }
  $env:Path = "$env:USERPROFILE\.local\bin;$env:USERPROFILE\.cargo\bin;" + $env:Path
}
if (Need "uv") {
  Write-Host "[ERROR] uv still not on PATH. Reopen PowerShell after install."
  Read-Host "Press Enter to exit"
  exit 1
}
Write-Host "[OK] $(uv --version)"

if (Need "ffmpeg") {
  if (Test-Path "C:\ffmpeg\bin\ffmpeg.exe") {
    $env:Path = "C:\ffmpeg\bin;" + $env:Path
  }
}
if (Need "ffmpeg") {
  Write-Host "Trying winget install FFmpeg ..."
  if (Get-Command winget -ErrorAction SilentlyContinue) {
    winget install --id Gyan.FFmpeg -e --accept-package-agreements --accept-source-agreements
  } else {
    Write-Host "[WARN] Install ffmpeg manually: https://www.gyan.dev/ffmpeg/builds/"
  }
}
if (-not (Need "ffmpeg")) { Write-Host "[OK] ffmpeg found" } else { Write-Host "[WARN] ffmpeg missing" }

if (-not (Test-Path ".\pyproject.toml")) {
  Write-Host "[ERROR] pyproject.toml not found. Run this script inside the project folder."
  Read-Host "Press Enter to exit"
  exit 1
}

Write-Host "uv sync ..."
uv sync
if ($LASTEXITCODE -ne 0) {
  Write-Host "[ERROR] uv sync failed"
  Read-Host "Press Enter to exit"
  exit 1
}
Write-Host "[OK] deps installed"
Write-Host "Done. Start with: .\start-win.bat   or   uv run python -m batch_watermark"
$go = Read-Host "Start GUI now? (Y/N)"
if ($go -match '^[Yy]') {
  uv run python -m batch_watermark
}
