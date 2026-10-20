"""界面偏好的读写：预览表显示字段与排序状态。"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Iterable

from .preview import COLUMN_KEYS, DEFAULT_VISIBLE, FIXED_COLUMNS

SETTINGS_VERSION = 1


def settings_path() -> Path:
    base = os.environ.get("APPDATA")
    root = Path(base) if base else Path.home() / ".config"
    return root / "FileOrganizer" / "settings.json"


def _read() -> dict:
    try:
        data = json.loads(settings_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _atomic_write(data: dict) -> None:
    """先写同目录临时文件再 os.replace，避免进程中断留下半截 JSON。"""
    path = settings_path()
    temp = path.with_name(path.name + ".tmp")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with temp.open("w", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(data, ensure_ascii=False, indent=2))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, path)
    except OSError:
        try:
            temp.unlink(missing_ok=True)
        except OSError:
            pass


def load_visible_columns() -> set[str]:
    """读取上次选择的字段；没有记录时返回默认字段。"""
    saved = _read().get("preview_columns")
    if not isinstance(saved, list):
        return set(DEFAULT_VISIBLE)
    visible = {key for key in saved if isinstance(key, str) and key in COLUMN_KEYS}
    return (visible | set(FIXED_COLUMNS)) or set(DEFAULT_VISIBLE)


def save_visible_columns(columns: Iterable[str]) -> None:
    """保存字段选择；写失败时静默忽略，不影响使用。"""
    data = _read()
    data["version"] = SETTINGS_VERSION
    data["preview_columns"] = [key for key in columns if key in COLUMN_KEYS]
    _atomic_write(data)


def load_preview_sort() -> tuple[str | None, bool]:
    """读取预览表排序；列名非法或缺失时回退为不排序。"""
    saved = _read().get("preview_sort")
    if not isinstance(saved, dict):
        return None, False
    column = saved.get("column")
    if not isinstance(column, str) or column not in COLUMN_KEYS:
        return None, False
    return column, bool(saved.get("descending", False))


def save_preview_sort(column: str | None, descending: bool = False) -> None:
    """保存排序列与方向；传 None 表示清除排序。"""
    data = _read()
    data["version"] = SETTINGS_VERSION
    if isinstance(column, str) and column in COLUMN_KEYS:
        data["preview_sort"] = {"column": column, "descending": bool(descending)}
    else:
        data.pop("preview_sort", None)
    _atomic_write(data)
