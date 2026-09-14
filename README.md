# 视频批量图片水印工具 (batch-watermark)

跨平台桌面应用：批量给 **视频** 叠加 **图片水印**（PNG/JPG，推荐透明 PNG）。

- 界面：PySide6（中文）
- 处理：ffmpeg `overlay` 滤镜 + H.264 编码（可选显卡编码器）
- 自动硬件检测（CPU/内存/显卡）+ CPU 利用率滑块（默认 90%）
- Windows 优先硬件编码：`h264_nvenc` / `h264_amf` / `h264_qsv`，失败自动回退 `libx264`
- 失败重试（指数退避）+ 失败列表一键重跑
- 包管理：`uv`

应用显示名：**视频批量图片水印工具**  
包名：`batch_watermark`

## 环境要求

- Python ≥ 3.10
- [uv](https://github.com/astral-sh/uv)
- **必需**：[ffmpeg](https://ffmpeg.org/)（处理视频）

### 安装 ffmpeg

**macOS**

```bash
brew install ffmpeg
```

**Windows**

1. 从 https://www.gyan.dev/ffmpeg/builds/ 或 https://github.com/BtbN/FFmpeg-Builds/releases 下载（若要用显卡编码，请选带 GPL/非 free 且包含 nvenc/amf/qsv 的构建）
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
4. 在新的终端中执行 `ffmpeg -version` 与 `ffmpeg -encoders | findstr h264` 确认可用

若未安装 ffmpeg，GUI 会明确提示，无法开始处理。

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

**macOS 桌面启动：** 双击仓库根目录的 `启动视频批量图片水印.command`（首次若被拦截，在「系统设置 → 隐私与安全性」允许）。

## 功能概览

| 功能 | 说明 |
|------|------|
| 输入 | 多选视频 / 文件夹扫描（仅 mp4/mov/mkv/avi/webm），支持拖放 |
| 水印 | **仅图片水印**：缩放、不透明度、九宫格位置、边距 |
| 输出 | 指定输出目录，原子写入（临时文件再替换） |
| 显卡 | 检测 GPU；「优先使用显卡编码」默认在检测到硬件编码器时开启 |
| CPU | 滑块 10%–100%，默认 90%；按逻辑核心与可用内存计算视频并发（有上限） |
| 控制 | 开始 / 暂停 / 继续 / 取消 |
| 进度 | 进度条、ETA、实时日志 |
| 失败 | 表格展示 +「重试失败项」 |

## 关于 GPU 加速（请读）

- **显卡编码**（NVENC / AMF / QSV）主要加速 **输出视频的压缩编码**，在 Windows 上收益通常最明显。
- 水印使用的 ffmpeg **`overlay` 滤镜目前仍主要在 CPU 上运行**（为保证兼容与稳定）。因此「开了显卡」不等于整条管线都进 GPU。
- 若硬件编码失败，工具会 **自动回退到 `libx264` 软件编码** 再试一次。
- 请使用包含对应编码器的 ffmpeg 构建；可用 `ffmpeg -encoders` 自查。

## 测试

```bash
uv run pytest -q
```

无 ffmpeg 时，依赖 ffmpeg 的视频用例会自动 skip。

## Windows 打包

```powershell
.\scripts\build-win.ps1
```

产物在 `dist\` 下。请另行提供 `ffmpeg.exe` 或让用户自行安装 ffmpeg。

## 许可

MIT
