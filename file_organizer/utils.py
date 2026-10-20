from __future__ import annotations

import sys
from pathlib import Path


def report_missing_gui_dependency(exc: ModuleNotFoundError) -> bool:
    """缺少界面依赖（CustomTkinter）时打印可操作提示，返回是否已处理。"""
    module = (exc.name or "").split(".")[0]
    if module not in {"customtkinter", "darkdetect"}:
        return False
    print(f"启动失败：当前 Python 解释器没有安装 CustomTkinter（缺少 {module}）。", file=sys.stderr)
    print(f"当前解释器：{sys.executable}", file=sys.stderr)
    print("请先安装依赖：python -m pip install -r requirements.txt", file=sys.stderr)
    print("如果在编辑器里运行，请把 Python 解释器切换为已安装依赖的那个。", file=sys.stderr)
    return True


def format_size(size: float) -> str:
    """把字节数格式化为便于阅读的字符串，例如 1.5 MB、512 B。"""
    value = float(size)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            if unit == "B":
                return f"{int(value)} B"
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} TB"


def normalize_extension(value: str) -> str:
    """统一扩展名：去空格、转小写、补前导点；空字符串表示“无扩展名”。"""
    cleaned = value.strip()
    if not cleaned:
        return ""
    return cleaned.casefold() if cleaned.startswith(".") else f".{cleaned.casefold()}"


def resource_path(relative: str) -> Path:
    """定位源码或 PyInstaller 打包后的资源文件。"""
    base = getattr(sys, "_MEIPASS", None)
    if base:
        return Path(base) / relative
    return Path(__file__).resolve().parent.parent / relative
