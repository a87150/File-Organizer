"""预览表的数据模型：字段定义、文件类型/修改时间格式化、排序。"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Sequence

from .core import TYPE_GROUPS, Action, ActionStatus
from .utils import format_size

# (字段名, 表头, 默认宽度, 对齐方式)
PREVIEW_COLUMNS: tuple[tuple[str, str, int, str], ...] = (
    ("status", "状态", 50, "w"),
    ("source", "原文件", 190, "w"),
    ("size", "大小", 72, "e"),
    ("file_type", "类型", 90, "w"),
    ("modified", "修改时间", 145, "w"),
    ("folder", "所在文件夹", 160, "w"),
    ("destination", "目标位置", 170, "w"),
)
COLUMN_KEYS = tuple(column[0] for column in PREVIEW_COLUMNS)
COLUMN_TITLES = {key: title for key, title, _, _ in PREVIEW_COLUMNS}
COLUMN_WIDTHS = {key: width for key, _, width, _ in PREVIEW_COLUMNS}
COLUMN_ANCHORS = {key: anchor for key, _, _, anchor in PREVIEW_COLUMNS}

# 「原文件」是每一行的核心信息，始终显示；其余列都可以在「显示字段」里开关。
FIXED_COLUMNS = ("source",)
DEFAULT_VISIBLE = ("status", "source", "destination", "file_type", "size", "modified")

# 扩展名 -> 中文类别（与重命名/查重页的类型分类保持一致）
EXTENSION_LABELS: dict[str, str] = {
    extension: category for category, extensions in TYPE_GROUPS.items() for extension in extensions
}

# 状态排序权重：分组标题在上，其余按操作阶段排列。
STATUS_ORDER = {
    "分组": 0,
    "保留": 1,
    "候选": 2,
    "匹配": 3,
    "待执行": 4,
    "成功": 5,
    "失败": 6,
    "已撤销": 7,
    "文件": 8,
}

_DIGITS = re.compile(r"(\d+)")


def file_type_label(path: Path) -> str:
    """把扩展名归类成便于阅读的类型，例如「图片 · .jpg」。"""
    suffix = path.suffix.casefold()
    if not suffix:
        return "无扩展名"
    category = EXTENSION_LABELS.get(suffix, "其他")
    return f"{category} · {suffix}"


def format_modified(timestamp: float | None) -> str:
    """格式化文件的最后修改时间。"""
    if timestamp is None:
        return "—"
    try:
        return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M")
    except (OSError, OverflowError, ValueError):
        return "—"


@dataclass(slots=True)
class PreviewRow:
    """预览表中的一行；显示文本与排序用的原始值分开保存。"""

    status: str = ""
    source: str = ""
    destination: str = ""
    file_type: str = ""
    size_text: str = ""
    modified: str = ""
    folder: str = ""
    size_value: int = -1
    modified_ts: float = 0.0
    tags: tuple[str, ...] = ()
    token: str | None = None
    parent_token: str | None = None
    group: int | None = None
    is_header: bool = False

    def value(self, key: str) -> str:
        if key == "size":
            return self.size_text
        return str(getattr(self, key, ""))


def build_action_row(
    action: Action,
    scan_root: Path | None,
    relative: Callable[[Path], str],
    folder_text: Callable[[Path], str],
) -> PreviewRow:
    """把一条 Action 转成预览行；目标/源文件只 stat 一次。"""
    target = action.destination
    try:
        info = target.stat()
    except OSError:
        target = action.source
        try:
            info = target.stat()
        except OSError:
            info = None

    if scan_root is not None:
        try:
            destination = str(action.destination.relative_to(scan_root))
        except ValueError:
            destination = str(action.destination)
    else:
        destination = str(action.destination)

    status = str(action.status)
    if action.status == ActionStatus.FAILED:
        tag = "failed"
    elif action.status in {ActionStatus.SUCCESS, ActionStatus.UNDONE}:
        tag = "success"
    else:
        tag = "pending"
    size = info.st_size if info is not None else None
    modified_ts = info.st_mtime if info is not None else 0.0
    return PreviewRow(
        status=status,
        source=relative(action.source),
        destination=destination,
        file_type=file_type_label(target),
        size_text=format_size(size) if size is not None else "—",
        modified=format_modified(modified_ts if info is not None else None),
        folder=folder_text(action.source),
        size_value=size if size is not None else -1,
        modified_ts=modified_ts,
        tags=(tag,),
    )



def natural_key(text: str) -> tuple:
    """文件名里的数字按数值比较：file2 排在 file10 前面。"""
    return tuple((0, int(part)) if part.isdigit() else (1, part.casefold()) for part in _DIGITS.split(text))


def _sort_key(row: PreviewRow, column: str):
    if column == "status":
        status = str(row.status)
        return STATUS_ORDER.get(status, 99), status
    if column == "size":
        return row.size_value
    if column == "modified":
        return row.modified_ts
    if column == "source":
        return natural_key(row.source)
    if column == "destination":
        return natural_key(row.destination)
    if column == "folder":
        return natural_key(row.folder)
    return str(getattr(row, column, "")).casefold()


def sort_preview_rows(rows: Sequence[PreviewRow], column: str, descending: bool = False) -> list[PreviewRow]:
    """按指定列排序。

    查重结果里带 ``group`` 的行是「分组标题 + 成员」的结构，此时只在组内排序成员，
    分组标题始终保持在该组第一行，避免把标题和成员拆散。
    """
    if column not in COLUMN_KEYS:
        return list(rows)
    key = lambda row: _sort_key(row, column)  # noqa: E731
    if not any(row.group is not None for row in rows):
        return sorted(rows, key=key, reverse=descending)

    blocks: dict[int, list[PreviewRow]] = {}
    order: list[int] = []
    for row in rows:
        group = row.group if row.group is not None else -1
        if group not in blocks:
            blocks[group] = []
            order.append(group)
        blocks[group].append(row)

    result: list[PreviewRow] = []
    for group in order:
        block = blocks[group]
        result.extend(row for row in block if row.is_header)
        members = [row for row in block if not row.is_header]
        members.sort(key=key, reverse=descending)
        result.extend(members)
    return result
