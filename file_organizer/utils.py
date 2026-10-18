from __future__ import annotations

import sys


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
    """把字节数格式化为便于阅读的字符串，例如 1.5 MB。"""
    value = float(size)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} TB"
