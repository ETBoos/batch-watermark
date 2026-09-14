#!/bin/bash
# macOS 桌面启动器 — 视频批量图片水印工具
set -euo pipefail
cd "$(dirname "$0")"
if ! command -v uv >/dev/null 2>&1; then
  echo "未找到 uv。请先安装: https://github.com/astral-sh/uv"
  echo "例如: brew install uv"
  read -r -p "按回车键退出…"
  exit 1
fi
uv sync --group dev
exec uv run python -m batch_watermark
