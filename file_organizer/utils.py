from __future__ import annotations


def format_size(size: float) -> str:
    """把字节数格式化为便于阅读的字符串，例如 1.5 MB。"""
    value = float(size)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} TB"
