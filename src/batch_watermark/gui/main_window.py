"""Main window — Chinese UI for batch watermark tool."""

from __future__ import annotations

import traceback
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, QThread, Signal, Slot
from PySide6.QtGui import QColor, QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QProgressBar,
    QSlider,
    QSpinBox,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
    QRadioButton,
    QButtonGroup,
    QColorDialog,
)

from batch_watermark import APP_DISPLAY_NAME, __version__
from batch_watermark.core.budget import compute_worker_budget
from batch_watermark.core.hardware import detect_hardware
from batch_watermark.core.queue import BatchProcessor, build_jobs, collect_input_files
from batch_watermark.engines.video_engine import ffmpeg_available, find_ffmpeg
from batch_watermark.models.job import JobStatus, MediaType, WatermarkJob
from batch_watermark.models.settings import (
    POSITION_LABELS_ZH,
    AppSettings,
    Position,
    WatermarkMode,
    WatermarkSettings,
    load_settings,
    save_settings,
)


class WorkerThread(QThread):
    progress = Signal(str, float, object)  # msg, fraction, eta
    log = Signal(str)
    job_done = Signal(object)
    finished_ok = Signal(object)

    def __init__(
        self,
        processor: BatchProcessor,
        jobs: list[WatermarkJob],
        settings: WatermarkSettings,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.processor = processor
        self.jobs = jobs
        self.settings = settings

    def run(self) -> None:
        try:
            budget = compute_worker_budget(self.settings.cpu_utilization)
            result = self.processor.run(
                self.jobs,
                self.settings,
                budget=budget,
                on_progress=lambda m, f, e: self.progress.emit(m, f, e),
                on_job_done=lambda j: self.job_done.emit(j),
                on_log=lambda m: self.log.emit(m),
            )
            self.finished_ok.emit(result)
        except Exception as exc:  # noqa: BLE001
            self.log.emit(f"致命错误: {exc}\n{traceback.format_exc()}")
            self.finished_ok.emit(None)


class DropListWidget(QListWidget):
    """File/folder list with drag-and-drop."""

    paths_dropped = Signal(list)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:  # noqa: N802
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event) -> None:  # noqa: N802
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event: QDropEvent) -> None:  # noqa: N802
        paths = []
        for url in event.mimeData().urls():
            local = url.toLocalFile()
            if local:
                paths.append(local)
        if paths:
            self.paths_dropped.emit(paths)
        event.acceptProposedAction()


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(f"{APP_DISPLAY_NAME} v{__version__}")
        self.resize(1100, 760)

        self._app_settings = load_settings()
        self._processor = BatchProcessor()
        self._worker: Optional[WorkerThread] = None
        self._jobs: list[WatermarkJob] = []
        self._running = False

        self._build_ui()
        self._apply_settings_to_ui(self._app_settings.watermark)
        self._refresh_hardware_label()
        self._refresh_ffmpeg_status()

    # ----- UI construction -----

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)

        splitter = QSplitter(Qt.Horizontal)
        root.addWidget(splitter)

        left = QWidget()
        left_layout = QVBoxLayout(left)
        splitter.addWidget(left)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        splitter.addWidget(right)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 4)

        # Input files
        input_box = QGroupBox("输入文件 / 文件夹（支持拖放）")
        input_l = QVBoxLayout(input_box)
        self.file_list = DropListWidget()
        self.file_list.paths_dropped.connect(self._add_paths)
        input_l.addWidget(self.file_list)
        btn_row = QHBoxLayout()
        self.btn_add_files = QPushButton("添加文件…")
        self.btn_add_folder = QPushButton("添加文件夹…")
        self.btn_clear_files = QPushButton("清空")
        self.btn_add_files.clicked.connect(self._add_files)
        self.btn_add_folder.clicked.connect(self._add_folder)
        self.btn_clear_files.clicked.connect(self.file_list.clear)
        btn_row.addWidget(self.btn_add_files)
        btn_row.addWidget(self.btn_add_folder)
        btn_row.addWidget(self.btn_clear_files)
        input_l.addLayout(btn_row)
        left_layout.addWidget(input_box)

        # Output
        out_box = QGroupBox("输出目录")
        out_l = QHBoxLayout(out_box)
        self.output_edit = QLineEdit()
        self.btn_out = QPushButton("浏览…")
        self.btn_out.clicked.connect(self._choose_output)
        out_l.addWidget(self.output_edit)
        out_l.addWidget(self.btn_out)
        left_layout.addWidget(out_box)

        # Watermark settings
        wm_box = QGroupBox("水印设置")
        form = QFormLayout(wm_box)

        mode_row = QHBoxLayout()
        self.radio_text = QRadioButton("文字水印")
        self.radio_image = QRadioButton("图片水印")
        self.radio_text.setChecked(True)
        self.mode_group = QButtonGroup(self)
        self.mode_group.addButton(self.radio_text)
        self.mode_group.addButton(self.radio_image)
        mode_row.addWidget(self.radio_text)
        mode_row.addWidget(self.radio_image)
        form.addRow("模式", mode_row)

        self.text_edit = QLineEdit("水印")
        form.addRow("文字内容", self.text_edit)

        font_row = QHBoxLayout()
        self.font_edit = QLineEdit()
        self.btn_font = QPushButton("字体…")
        self.btn_font.clicked.connect(self._choose_font)
        font_row.addWidget(self.font_edit)
        font_row.addWidget(self.btn_font)
        form.addRow("字体文件", font_row)

        self.font_size = QSpinBox()
        self.font_size.setRange(8, 512)
        self.font_size.setValue(36)
        form.addRow("字号", self.font_size)

        color_row = QHBoxLayout()
        self.color_edit = QLineEdit("#FFFFFF")
        self.btn_color = QPushButton("选色…")
        self.btn_color.clicked.connect(self._choose_color)
        color_row.addWidget(self.color_edit)
        color_row.addWidget(self.btn_color)
        form.addRow("颜色", color_row)

        self.opacity = QDoubleSpinBox()
        self.opacity.setRange(0.05, 1.0)
        self.opacity.setSingleStep(0.05)
        self.opacity.setValue(0.5)
        form.addRow("不透明度", self.opacity)

        self.rotation = QDoubleSpinBox()
        self.rotation.setRange(-180, 180)
        self.rotation.setSuffix(" °")
        form.addRow("旋转", self.rotation)

        img_row = QHBoxLayout()
        self.wm_image_edit = QLineEdit()
        self.btn_wm_image = QPushButton("选择…")
        self.btn_wm_image.clicked.connect(self._choose_wm_image)
        img_row.addWidget(self.wm_image_edit)
        img_row.addWidget(self.btn_wm_image)
        form.addRow("水印图片", img_row)

        self.image_scale = QDoubleSpinBox()
        self.image_scale.setRange(0.01, 1.0)
        self.image_scale.setSingleStep(0.05)
        self.image_scale.setValue(0.2)
        form.addRow("图片缩放(相对宽)", self.image_scale)

        self.position = QComboBox()
        for pos, label in POSITION_LABELS_ZH.items():
            self.position.addItem(label, pos)
        # default bottom-right
        idx = list(POSITION_LABELS_ZH.keys()).index(Position.BOTTOM_RIGHT)
        self.position.setCurrentIndex(idx)
        form.addRow("位置(九宫格)", self.position)

        self.margin = QSpinBox()
        self.margin.setRange(0, 500)
        self.margin.setValue(20)
        form.addRow("边距(px)", self.margin)

        left_layout.addWidget(wm_box)

        # CPU / hardware
        hw_box = QGroupBox("硬件与并发")
        hw_form = QFormLayout(hw_box)
        self.hw_label = QLabel()
        hw_form.addRow("检测结果", self.hw_label)

        cpu_row = QHBoxLayout()
        self.cpu_slider = QSlider(Qt.Horizontal)
        self.cpu_slider.setRange(10, 100)
        self.cpu_slider.setValue(90)
        self.cpu_slider.setTickInterval(10)
        self.cpu_slider.setTickPosition(QSlider.TicksBelow)
        self.cpu_value = QLabel("90%")
        self.cpu_slider.valueChanged.connect(lambda v: self.cpu_value.setText(f"{v}%"))
        self.cpu_slider.valueChanged.connect(lambda _v: self._refresh_budget_hint())
        cpu_row.addWidget(self.cpu_slider)
        cpu_row.addWidget(self.cpu_value)
        hw_form.addRow("CPU 利用率", cpu_row)

        self.budget_hint = QLabel()
        hw_form.addRow("预计并发", self.budget_hint)

        self.max_retries = QSpinBox()
        self.max_retries.setRange(0, 10)
        self.max_retries.setValue(3)
        hw_form.addRow("最大重试次数", self.max_retries)

        self.ffmpeg_label = QLabel()
        hw_form.addRow("ffmpeg", self.ffmpeg_label)
        left_layout.addWidget(hw_box)

        # Controls
        ctrl = QHBoxLayout()
        self.btn_start = QPushButton("开始")
        self.btn_pause = QPushButton("暂停")
        self.btn_resume = QPushButton("继续")
        self.btn_cancel = QPushButton("取消")
        self.btn_retry = QPushButton("重试失败项")
        self.btn_pause.setEnabled(False)
        self.btn_resume.setEnabled(False)
        self.btn_cancel.setEnabled(False)
        self.btn_start.clicked.connect(self._start)
        self.btn_pause.clicked.connect(self._pause)
        self.btn_resume.clicked.connect(self._resume)
        self.btn_cancel.clicked.connect(self._cancel)
        self.btn_retry.clicked.connect(self._retry_failed)
        for b in (
            self.btn_start,
            self.btn_pause,
            self.btn_resume,
            self.btn_cancel,
            self.btn_retry,
        ):
            ctrl.addWidget(b)
        left_layout.addLayout(ctrl)

        # Right: progress, log, failed table
        self.progress = QProgressBar()
        self.progress.setRange(0, 1000)
        self.progress.setValue(0)
        right_layout.addWidget(self.progress)

        self.eta_label = QLabel("进度: — | 预计剩余: —")
        right_layout.addWidget(self.eta_label)

        self.log_view = QTextEdit()
        self.log_view.setReadOnly(True)
        right_layout.addWidget(QLabel("实时日志"))
        right_layout.addWidget(self.log_view, stretch=2)

        right_layout.addWidget(QLabel("失败列表"))
        self.fail_table = QTableWidget(0, 3)
        self.fail_table.setHorizontalHeaderLabels(["文件", "错误", "尝试次数"])
        self.fail_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.fail_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.fail_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        right_layout.addWidget(self.fail_table, stretch=1)

        self.statusBar().showMessage("就绪")

    # ----- helpers -----

    def _refresh_hardware_label(self) -> None:
        hw = detect_hardware()
        self.hw_label.setText(
            f"物理核心 {hw.physical_cores} / 逻辑核心 {hw.logical_cores} | "
            f"内存 {hw.available_ram_gb:.1f}/{hw.total_ram_gb:.1f} GB 可用"
        )
        self._refresh_budget_hint()

    def _refresh_budget_hint(self) -> None:
        budget = compute_worker_budget(self.cpu_slider.value())
        self.budget_hint.setText(
            f"图片 {budget.image_workers} 并发 · 视频 {budget.video_workers} 并发"
        )

    def _refresh_ffmpeg_status(self) -> None:
        path = find_ffmpeg()
        if path:
            self.ffmpeg_label.setText(f"已找到: {path}")
            self.ffmpeg_label.setStyleSheet("color: green;")
        else:
            self.ffmpeg_label.setText(
                "未找到 — 视频功能不可用。请安装 ffmpeg 并加入 PATH"
                "（Windows 常见路径见 README）"
            )
            self.ffmpeg_label.setStyleSheet("color: #b00020;")

    def _apply_settings_to_ui(self, wm: WatermarkSettings) -> None:
        self.radio_text.setChecked(wm.mode == WatermarkMode.TEXT)
        self.radio_image.setChecked(wm.mode == WatermarkMode.IMAGE)
        self.text_edit.setText(wm.text)
        self.font_edit.setText(wm.font_path)
        self.font_size.setValue(wm.font_size)
        self.color_edit.setText(wm.color)
        self.opacity.setValue(wm.opacity)
        self.rotation.setValue(wm.rotation)
        self.wm_image_edit.setText(wm.image_path)
        self.image_scale.setValue(wm.image_scale)
        for i in range(self.position.count()):
            if self.position.itemData(i) == wm.position:
                self.position.setCurrentIndex(i)
                break
        self.margin.setValue(wm.margin)
        self.cpu_slider.setValue(wm.cpu_utilization)
        self.max_retries.setValue(wm.max_retries)
        self.output_edit.setText(wm.output_dir)

    def _collect_settings_from_ui(self) -> WatermarkSettings:
        mode = WatermarkMode.IMAGE if self.radio_image.isChecked() else WatermarkMode.TEXT
        pos = self.position.currentData()
        if not isinstance(pos, Position):
            pos = Position.BOTTOM_RIGHT
        return WatermarkSettings(
            mode=mode,
            text=self.text_edit.text(),
            font_path=self.font_edit.text().strip(),
            font_size=self.font_size.value(),
            color=self.color_edit.text().strip() or "#FFFFFF",
            opacity=float(self.opacity.value()),
            rotation=float(self.rotation.value()),
            image_path=self.wm_image_edit.text().strip(),
            image_scale=float(self.image_scale.value()),
            position=pos,
            margin=self.margin.value(),
            cpu_utilization=self.cpu_slider.value(),
            max_retries=self.max_retries.value(),
            output_dir=self.output_edit.text().strip(),
            last_input_dir=self._app_settings.watermark.last_input_dir,
        )

    def _persist(self) -> None:
        wm = self._collect_settings_from_ui()
        self._app_settings = AppSettings(watermark=wm)
        try:
            save_settings(self._app_settings)
        except OSError as exc:
            self._append_log(f"保存设置失败: {exc}")

    def _append_log(self, msg: str) -> None:
        self.log_view.append(msg)

    def _current_input_paths(self) -> list[Path]:
        paths: list[Path] = []
        for i in range(self.file_list.count()):
            paths.append(Path(self.file_list.item(i).text()))
        return paths

    @Slot(list)
    def _add_paths(self, paths: list) -> None:
        existing = {self.file_list.item(i).text() for i in range(self.file_list.count())}
        for p in paths:
            s = str(p)
            if s not in existing:
                self.file_list.addItem(s)
                existing.add(s)

    def _add_files(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "选择图片或视频",
            self._app_settings.watermark.last_input_dir or "",
            "媒体文件 (*.jpg *.jpeg *.png *.webp *.bmp *.tif *.tiff *.mp4 *.mov *.mkv *.avi *.webm);;所有文件 (*)",
        )
        if files:
            self._app_settings.watermark.last_input_dir = str(Path(files[0]).parent)
            self._add_paths(files)

    def _add_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self, "选择文件夹", self._app_settings.watermark.last_input_dir or ""
        )
        if folder:
            self._app_settings.watermark.last_input_dir = folder
            self._add_paths([folder])

    def _choose_output(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self, "选择输出目录", self.output_edit.text() or ""
        )
        if folder:
            self.output_edit.setText(folder)

    def _choose_font(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "选择字体文件",
            "",
            "字体 (*.ttf *.otf *.ttc);;所有文件 (*)",
        )
        if path:
            self.font_edit.setText(path)

    def _choose_wm_image(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "选择水印图片",
            "",
            "图片 (*.png *.jpg *.jpeg *.webp *.bmp);;所有文件 (*)",
        )
        if path:
            self.wm_image_edit.setText(path)

    def _choose_color(self) -> None:
        initial = QColor(self.color_edit.text() or "#FFFFFF")
        color = QColorDialog.getColor(initial, self, "选择水印颜色")
        if color.isValid():
            self.color_edit.setText(color.name().upper())

    def _set_running_ui(self, running: bool) -> None:
        self._running = running
        self.btn_start.setEnabled(not running)
        self.btn_retry.setEnabled(not running)
        self.btn_pause.setEnabled(running)
        self.btn_resume.setEnabled(False)
        self.btn_cancel.setEnabled(running)

    def _validate_before_start(self, settings: WatermarkSettings) -> Optional[str]:
        if self.file_list.count() == 0:
            return "请先添加输入文件或文件夹"
        if not settings.output_dir:
            return "请选择输出目录"
        out = Path(settings.output_dir)
        if not out.exists():
            try:
                out.mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                return f"无法创建输出目录: {exc}"
        if settings.mode == WatermarkMode.IMAGE and not (
            settings.image_path and Path(settings.image_path).is_file()
        ):
            return "图片水印模式下请选择有效的水印图片"
        if settings.mode == WatermarkMode.TEXT and not (settings.text or "").strip():
            return "请输入水印文字"
        return None

    def _start_jobs(self, jobs: list[WatermarkJob]) -> None:
        if not jobs:
            QMessageBox.warning(self, "提示", "没有可处理的图片/视频文件")
            return
        has_video = any(j.media_type == MediaType.VIDEO for j in jobs)
        if has_video and not ffmpeg_available():
            QMessageBox.warning(
                self,
                "缺少 ffmpeg",
                "检测到视频文件，但系统未找到 ffmpeg。\n"
                "视频任务将失败。请安装 ffmpeg 后重试。\n\n"
                "macOS: brew install ffmpeg\n"
                "Windows: 见 README 安装说明，或将 ffmpeg.exe 加入 PATH。",
            )
        settings = self._collect_settings_from_ui()
        self._persist()
        self._jobs = jobs
        self.fail_table.setRowCount(0)
        self.progress.setValue(0)
        self._append_log(f"开始处理 {len(jobs)} 个任务…")
        self._processor = BatchProcessor()
        self._worker = WorkerThread(self._processor, jobs, settings, self)
        self._worker.progress.connect(self._on_progress)
        self._worker.log.connect(self._append_log)
        self._worker.job_done.connect(self._on_job_done)
        self._worker.finished_ok.connect(self._on_finished)
        self._set_running_ui(True)
        self._worker.start()

    def _start(self) -> None:
        settings = self._collect_settings_from_ui()
        err = self._validate_before_start(settings)
        if err:
            QMessageBox.warning(self, "无法开始", err)
            return
        sources = collect_input_files(self._current_input_paths())
        jobs = build_jobs(sources, Path(settings.output_dir))
        self._start_jobs(jobs)

    def _retry_failed(self) -> None:
        failed = [j for j in self._jobs if j.status == JobStatus.FAILED]
        if not failed:
            QMessageBox.information(self, "提示", "没有失败任务可重试")
            return
        # Reset failed jobs
        for j in failed:
            j.status = JobStatus.PENDING
            j.error = None
            j.attempts = 0
        self._start_jobs(failed)

    def _pause(self) -> None:
        self._processor.pause()
        self.btn_pause.setEnabled(False)
        self.btn_resume.setEnabled(True)
        self._append_log("已暂停")
        self.statusBar().showMessage("已暂停")

    def _resume(self) -> None:
        self._processor.resume()
        self.btn_pause.setEnabled(True)
        self.btn_resume.setEnabled(False)
        self._append_log("继续处理…")
        self.statusBar().showMessage("处理中…")

    def _cancel(self) -> None:
        self._processor.cancel()
        self._append_log("正在取消…")
        self.statusBar().showMessage("正在取消…")

    @Slot(str, float, object)
    def _on_progress(self, msg: str, fraction: float, eta) -> None:
        self.progress.setValue(int(fraction * 1000))
        if eta is None:
            eta_s = "—"
        else:
            eta_s = f"{int(eta)} 秒"
        self.eta_label.setText(f"进度: {msg} ({fraction * 100:.1f}%) | 预计剩余: {eta_s}")
        self.statusBar().showMessage(f"处理中 {msg}")

    @Slot(object)
    def _on_job_done(self, job: object) -> None:
        if not isinstance(job, WatermarkJob):
            return
        if job.status == JobStatus.FAILED:
            row = self.fail_table.rowCount()
            self.fail_table.insertRow(row)
            self.fail_table.setItem(row, 0, QTableWidgetItem(str(job.source)))
            self.fail_table.setItem(row, 1, QTableWidgetItem(job.error or ""))
            self.fail_table.setItem(row, 2, QTableWidgetItem(str(job.attempts)))

    @Slot(object)
    def _on_finished(self, result: object) -> None:
        self._set_running_ui(False)
        self._worker = None
        if result is None:
            self.statusBar().showMessage("异常结束")
            return
        failed = result.failed
        ok = result.succeeded
        self._append_log(f"全部结束: 成功 {len(ok)}，失败 {len(failed)}")
        self.statusBar().showMessage(f"完成 — 成功 {len(ok)} / 失败 {len(failed)}")
        self.progress.setValue(1000)
        if failed:
            QMessageBox.warning(
                self,
                "部分失败",
                f"成功 {len(ok)}，失败 {len(failed)}。\n可在失败列表中查看，并点击「重试失败项」。",
            )

    def closeEvent(self, event) -> None:  # noqa: N802
        self._persist()
        if self._running and self._worker and self._worker.isRunning():
            self._processor.cancel()
            self._worker.wait(3000)
        super().closeEvent(event)
