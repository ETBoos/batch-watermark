"""Hardware detection: CPU/RAM via psutil, GPU via platform tools."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from typing import Optional

import psutil


@dataclass(frozen=True)
class HardwareInfo:
    """Detected CPU / RAM snapshot."""

    physical_cores: int
    logical_cores: int
    total_ram_bytes: int
    available_ram_bytes: int

    @property
    def total_ram_gb(self) -> float:
        return self.total_ram_bytes / (1024**3)

    @property
    def available_ram_gb(self) -> float:
        return self.available_ram_bytes / (1024**3)


@dataclass(frozen=True)
class GpuInfo:
    """Detected GPU summary (best-effort)."""

    names: tuple[str, ...] = ()
    vendor_hints: tuple[str, ...] = ()  # nvidia / amd / intel
    raw: str = ""

    @property
    def available(self) -> bool:
        return bool(self.names)

    @property
    def summary(self) -> str:
        if not self.names:
            return "未检测到独立/可用显卡信息"
        return "、".join(self.names)


def detect_hardware() -> HardwareInfo:
    physical = psutil.cpu_count(logical=False) or 1
    logical = psutil.cpu_count(logical=True) or physical
    mem = psutil.virtual_memory()
    return HardwareInfo(
        physical_cores=int(physical),
        logical_cores=int(logical),
        total_ram_bytes=int(mem.total),
        available_ram_bytes=int(mem.available),
    )


def _run_capture(cmd: list[str], timeout: float = 8.0) -> Optional[str]:
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0 and not (proc.stdout or "").strip():
        return None
    return (proc.stdout or "") + (proc.stderr or "")


def _vendor_from_name(name: str) -> Optional[str]:
    lower = name.lower()
    if any(k in lower for k in ("nvidia", "geforce", "quadro", "rtx", "gtx", "tesla")):
        return "nvidia"
    if any(k in lower for k in ("amd", "radeon", "rx ", "vega", "firepro")):
        return "amd"
    if any(k in lower for k in ("intel", "arc", "uhd", "iris", "xe ")):
        return "intel"
    # Apple Silicon / macOS GPU (VideoToolbox)
    if any(k in lower for k in ("apple", "m1", "m2", "m3", "m4", "m5", "paravirtual")):
        return "apple"
    return None


def _gpus_from_nvidia_smi() -> list[str]:
    smi = shutil.which("nvidia-smi")
    if not smi:
        return []
    out = _run_capture([smi, "--query-gpu=name", "--format=csv,noheader"])
    if not out:
        return []
    names = []
    for line in out.splitlines():
        line = line.strip()
        if line and "NVIDIA-SMI" not in line and "failed" not in line.lower():
            names.append(line)
    return names


def _gpus_from_windows() -> list[str]:
    if os.name != "nt":
        return []
    # Prefer PowerShell CIM (works without WMIC on newer Windows)
    ps = (
        "Get-CimInstance Win32_VideoController | "
        "Select-Object -ExpandProperty Name"
    )
    out = _run_capture(
        ["powershell", "-NoProfile", "-Command", ps],
        timeout=12.0,
    )
    names: list[str] = []
    if out:
        for line in out.splitlines():
            line = line.strip()
            if line and not line.lower().startswith("get-ciminstance"):
                names.append(line)
    if names:
        return names
    out = _run_capture(
        ["wmic", "path", "win32_VideoController", "get", "name"],
        timeout=12.0,
    )
    if not out:
        return []
    for line in out.splitlines():
        line = line.strip()
        if not line or line.lower() == "name":
            continue
        names.append(line)
    return names


def _gpus_from_macos() -> list[str]:
    if os.name == "nt":
        return []
    # system_profiler is macOS-only
    out = _run_capture(
        ["system_profiler", "SPDisplaysDataType", "-detailLevel", "mini"],
        timeout=15.0,
    )
    if not out:
        return []
    names: list[str] = []
    for line in out.splitlines():
        m = re.match(r"\s*Chipset Model:\s*(.+)\s*$", line)
        if m:
            names.append(m.group(1).strip())
            continue
        m = re.match(r"\s*([A-Za-z0-9].+):\s*$", line)
        # Ignore section headers that aren't chipsets
    return names


def detect_gpu() -> GpuInfo:
    """Best-effort GPU detection across Windows / NVIDIA / macOS."""
    names: list[str] = []
    raw_parts: list[str] = []

    nv = _gpus_from_nvidia_smi()
    if nv:
        names.extend(nv)
        raw_parts.append("nvidia-smi: " + "; ".join(nv))

    if os.name == "nt":
        win = _gpus_from_windows()
        for n in win:
            if n not in names:
                names.append(n)
        if win:
            raw_parts.append("Win32_VideoController: " + "; ".join(win))
    else:
        mac = _gpus_from_macos()
        for n in mac:
            if n not in names:
                names.append(n)
        if mac:
            raw_parts.append("system_profiler: " + "; ".join(mac))

    vendors: list[str] = []
    for n in names:
        v = _vendor_from_name(n)
        if v and v not in vendors:
            vendors.append(v)

    return GpuInfo(
        names=tuple(names),
        vendor_hints=tuple(vendors),
        raw=" | ".join(raw_parts),
    )
