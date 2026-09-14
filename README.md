# 批量水印工具 (batch-watermark)

跨平台桌面应用：批量给**图片**和**视频**添加文字/图片水印。

- 界面：PySide6（中文）
- 图片引擎：Pillow
- 视频引擎：ffmpeg（subprocess）
- 自动硬件检测（psutil）+ CPU 利用率滑块（默认 90%）
- 失败重试（指数退避）+ 失败列表一键重跑
- 包管理：`uv`

应用显示名：**批量水印工具**  
包名：`batch_watermark`

## 环境要求

- Python ≥ 3.10
- [uv](https://github.com/astral-sh/uv)
- （可选，处理视频时必需）[ffmpeg](https://ffmpeg.org/)

### 安装 ffmpeg

**macOS**

```bash
brew install ffmpeg
```

**Windows**

1. 从 https://www.gyan.dev/ffmpeg/builds/ 或 https://github.com/BtbN/FFmpeg-Builds/releases 下载
2. 解压后将 `bin` 目录加入系统 PATH，或放到常见位置之一：
   - `C:\ffmpeg\bin\ffmpeg.exe`
   - `C:\Program Files\ffmpeg\bin\ffmpeg.exe`
3. 也可用包管理器：
   ```powershell
   winget install ffmpeg
   # 或
   choco install ffmpeg
   # 或
   scoop install ffmpeg
   ```
4. 在新的终端中执行 `ffmpeg -version` 确认可用

若未安装 ffmpeg，GUI 会明确提示，视频任务将被禁用/失败，图片任务不受影响。

## 安装与运行

```bash
cd batch-watermark
uv sync --group dev
uv run python -m batch_watermark
```

或：

```bash
uv run batch-watermark
```

## 功能概览

| 功能 | 说明 |
|------|------|
| 输入 | 多选文件 / 文件夹，支持拖放 |
| 输出 | 指定输出目录，原子写入（临时文件再替换） |
| 文字水印 | 字体、字号、颜色、不透明度、旋转 |
| 图片水印 | 缩放比例、不透明度、旋转 |
| 位置 | 九宫格 + 边距 |
| 图片格式 | jpg/jpeg/png/webp/bmp/tiff |
| 视频格式 | mp4/mov/mkv/avi/webm（保留音轨） |
| CPU | 滑块 10%–100%，默认 90%；按逻辑核心与可用内存计算并发 |
| 重试 | 默认最多 3 次，指数退避 |
| 失败 | 表格展示 +「重试失败项」 |

## 测试

```bash
uv run pytest
```

无 ffmpeg 时视频相关用例会自动 skip。

## Windows 打包（PyInstaller）

见 `scripts/build-win.ps1`：

```powershell
# 在 Windows 上、已安装 uv / Python 的环境中：
cd batch-watermark
.\scripts\build-win.ps1
```

产物在 `dist/批量水印工具/`（或 `dist/batch-watermark/`）。请自行将 `ffmpeg.exe` 一并分发或要求用户安装。

## 项目结构

```
batch-watermark/
  pyproject.toml
  README.md
  src/batch_watermark/
    __init__.py
    __main__.py
    app.py
    gui/main_window.py
    core/hardware.py
    core/budget.py
    core/retry.py
    core/queue.py
    engines/image_engine.py
    engines/video_engine.py
    models/job.py
    models/settings.py
  tests/
  scripts/build-win.ps1
```

## 设置持久化

设置保存在用户配置目录下的 `settings.json`（并镜像到 QSettings）：

- macOS: `~/Library/Application Support/batch_watermark/`
- Windows: `%LOCALAPPDATA%\batch_watermark\`
- Linux: `~/.config/batch_watermark/`

## 许可证

MIT
