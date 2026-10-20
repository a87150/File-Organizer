"""界面偏好的读写：目前保存预览表要显示的字段。"""

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
    try:
        path = settings_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        pass
