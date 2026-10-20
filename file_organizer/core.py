from __future__ import annotations

import json
import os
import re
import shutil
from dataclasses import dataclass
from datetime import date, datetime, time
from enum import Enum
from pathlib import Path
from typing import Iterable, Literal

from .duplicates import (
    KIND_ORDER,
    DuplicateGroup,
    DuplicateOptions,
    DuplicateResult,
    find_duplicates as find_duplicates_paths,
    find_duplicates_entries,
    order_group_members,
)
from .utils import normalize_extension


INVALID_WINDOWS_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')

# 扫描时永远跳过的工具目录，避免把撤销日志当成待整理文件。
LOG_DIRECTORY_NAME = ".file_organizer_logs"
# Windows FILE_ATTRIBUTE_HIDDEN；其他平台的 stat 结果没有这个字段。
FILE_ATTRIBUTE_HIDDEN = 0x2
MAX_COMPONENT_LENGTH = 255


class ActionStatus(str, Enum):
    """操作状态。枚举值仍是中文，日志与界面显示保持兼容。"""

    PENDING = "待执行"
    SUCCESS = "成功"
    FAILED = "失败"
    UNDONE = "已撤销"

    def __str__(self) -> str:
        return self.value


STATUS_PENDING = ActionStatus.PENDING
STATUS_SUCCESS = ActionStatus.SUCCESS
STATUS_FAILED = ActionStatus.FAILED
STATUS_UNDONE = ActionStatus.UNDONE

TYPE_GROUPS: dict[str, set[str]] = {
    "图片": {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".svg", ".ico", ".heic", ".raw"},
    "视频": {
        ".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv", ".webm", ".m4v",
        ".mpg", ".mpeg", ".ts", ".m2ts", ".3gp", ".rmvb", ".vob", ".ogv", ".divx",
    },
    "音频": {".mp3", ".wav", ".flac", ".aac", ".ogg", ".m4a", ".wma"},
    "文档": {".doc", ".docx", ".pdf", ".txt", ".md", ".rtf", ".odt", ".ppt", ".pptx", ".xls", ".xlsx", ".csv"},
    "压缩包": {".zip", ".rar", ".7z", ".tar", ".gz", ".bz2", ".xz"},
    "程序与安装包": {".exe", ".msi", ".msix", ".apk", ".appx", ".bat", ".cmd", ".ps1", ".sh"},
    "代码": {".py", ".js", ".ts", ".tsx", ".jsx", ".java", ".c", ".cpp", ".h", ".cs", ".go", ".rs", ".html", ".css", ".json", ".xml", ".yaml", ".yml"},
    "镜像": {".iso", ".wim", ".img", ".vhd", ".vhdx"},
}


@dataclass(frozen=True)
class FileEntry:
    """扫描结果：路径与扫描时已经取得的 stat 信息。"""

    path: Path
    size: int | None = None
    mtime: float | None = None


@dataclass(frozen=True)
class RenameOptions:
    prefix: str = ""
    suffix: str = ""
    find: str = ""
    replace: str = ""
    use_regex: bool = False
    case: Literal["keep", "lower", "upper", "title"] = "keep"
    add_counter: bool = False
    counter_start: int = 1
    counter_width: int = 3
    new_extension: str = ""


@dataclass(frozen=True)
class SearchOptions:
    name_pattern: str = ""
    use_regex: bool = False
    extensions: tuple[str, ...] = ()
    min_size_mb: float | None = None
    max_size_mb: float | None = None
    modified_from: date | None = None
    modified_to: date | None = None


@dataclass(frozen=True)
class OrganizeOptions:
    mode: Literal["type", "extension", "name", "extract", "date", "size"] = "type"
    name_rules: tuple[tuple[str, str], ...] = ()
    extract_pattern: str = ""
    extract_group: str = "1"
    include_other: bool = True


@dataclass(frozen=True)
class CleanupOptions:
    kinds: tuple[str, ...] = ("hash",)
    keeper: Literal["oldest", "newest", "shortest-path", "first"] = "oldest"
    folder_name: str = "重复文件"
    group_subfolders: bool = True


@dataclass(frozen=True)
class Action:
    operation: Literal["rename", "move"]
    source: Path
    destination: Path
    status: ActionStatus = ActionStatus.PENDING
    message: str = ""


def sanitize_component(value: str, *, max_length: int = MAX_COMPONENT_LENGTH) -> str:
    """清理文件名组件；超过文件系统长度上限时截断（扩展名由调用方保留）。"""
    value = INVALID_WINDOWS_CHARS.sub("_", value).strip().rstrip(".")
    if max_length > 0 and len(value) > max_length:
        value = value[:max_length].rstrip(" .")
    return value or "未命名"


def _reserved_key(path: Path) -> str:
    """Windows 文件系统大小写不敏感，reserved 统一用 normcase 后的字符串。"""
    return os.path.normcase(str(path))


def unique_path(path: Path, reserved: set[str] | None = None) -> Path:
    reserved = reserved or set()
    if not path.exists() and _reserved_key(path) not in reserved:
        return path
    counter = 1
    while True:
        suffix = f" ({counter})"
        max_stem = max(1, MAX_COMPONENT_LENGTH - len(path.suffix) - len(suffix))
        candidate = path.with_name(f"{path.stem[:max_stem].rstrip(' .')}{suffix}{path.suffix}")
        if not candidate.exists() and _reserved_key(candidate) not in reserved:
            return candidate
        counter += 1


class OrganizerEngine:
    def scan(self, folder: Path, recursive: bool = False, include_hidden: bool = False) -> list[FileEntry]:
        folder = folder.expanduser().resolve()
        if not folder.is_dir():
            raise ValueError(f"文件夹不存在：{folder}")
        files: list[FileEntry] = []
        stack = [folder]
        while stack:
            current = stack.pop()
            try:
                entries = list(os.scandir(current))
            except OSError:
                continue
            for entry in entries:
                name = entry.name
                try:
                    is_directory = entry.is_dir(follow_symlinks=False)
                except OSError:
                    continue
                # 日志目录在任何情况下都不参与扫描，即使勾选了“包含隐藏文件”。
                if is_directory and name == LOG_DIRECTORY_NAME:
                    continue
                try:
                    info = entry.stat(follow_symlinks=False)
                except OSError:
                    info = None
                if not include_hidden and (name.startswith(".") or self._has_hidden_attribute(info)):
                    continue
                if is_directory:
                    if recursive:
                        stack.append(Path(entry.path))
                    continue
                try:
                    if not entry.is_file():
                        continue
                except OSError:
                    continue
                if info is None:
                    files.append(FileEntry(Path(entry.path)))
                else:
                    files.append(FileEntry(Path(entry.path), info.st_size, info.st_mtime))
        return sorted(files, key=lambda item: str(item.path).casefold())

    @staticmethod
    def _has_hidden_attribute(info: os.stat_result | None) -> bool:
        """Windows 隐藏属性；其他平台 stat 没有 st_file_attributes 时返回 False。"""
        attributes = getattr(info, "st_file_attributes", 0) if info is not None else 0
        return bool(attributes & FILE_ATTRIBUTE_HIDDEN)

    def filter_files(self, files: Iterable[FileEntry | Path], options: SearchOptions) -> list[FileEntry]:
        """按条件筛选，尽量复用扫描阶段缓存的 size / mtime。"""
        pattern = re.compile(options.name_pattern, re.IGNORECASE) if options.name_pattern and options.use_regex else None
        extensions = {normalize_extension(value) for value in options.extensions}
        minimum = options.min_size_mb * 1024 * 1024 if options.min_size_mb is not None else None
        maximum = options.max_size_mb * 1024 * 1024 if options.max_size_mb is not None else None
        modified_from = datetime.combine(options.modified_from, time.min).timestamp() if options.modified_from else None
        modified_to = datetime.combine(options.modified_to, time.max).timestamp() if options.modified_to else None
        matches: list[FileEntry] = []
        for item in files:
            entry = item if isinstance(item, FileEntry) else FileEntry(item)
            path = entry.path
            if options.name_pattern:
                name_matches = bool(pattern.search(path.name)) if pattern else options.name_pattern.casefold() in path.name.casefold()
                if not name_matches:
                    continue
            if extensions and path.suffix.casefold() not in extensions:
                continue
            # 预览与执行之间文件可能被移走；缓存值仍要配合存在性检查。
            if not path.exists():
                continue
            size = entry.size
            modified = entry.mtime
            if size is None or modified is None:
                try:
                    info = path.stat()
                except OSError:
                    continue
                size, modified = info.st_size, info.st_mtime
            if minimum is not None and size < minimum:
                continue
            if maximum is not None and size > maximum:
                continue
            if modified_from is not None and modified < modified_from:
                continue
            if modified_to is not None and modified > modified_to:
                continue
            matches.append(FileEntry(path, size, modified))
        return matches

    def preview_rename(self, files: Iterable[Path], options: RenameOptions) -> list[Action]:
        actions: list[Action] = []
        reserved: set[str] = set()
        for index, source in enumerate(files, options.counter_start):
            stem = source.stem
            if options.find:
                stem = re.sub(options.find, options.replace, stem) if options.use_regex else stem.replace(options.find, options.replace)
            if options.case == "lower":
                stem = stem.lower()
            elif options.case == "upper":
                stem = stem.upper()
            elif options.case == "title":
                stem = stem.title()
            counter = f"_{index:0{max(1, options.counter_width)}d}" if options.add_counter else ""
            extension = source.suffix
            if options.new_extension.strip():
                extension = self._normalize_extension(options.new_extension)
            # 截断时预留扩展名长度；若追加 (1) 之类的重名后缀，unique_path 会再截断一次。
            new_stem = sanitize_component(
                f"{options.prefix}{stem}{options.suffix}{counter}",
                max_length=max(1, MAX_COMPONENT_LENGTH - len(extension)),
            )
            destination = unique_path(source.with_name(new_stem + extension), reserved)
            reserved.add(_reserved_key(destination))
            if source != destination:
                actions.append(Action("rename", source, destination))
        return actions

    @staticmethod
    def _normalize_extension(value: str) -> str:
        extension = value.strip().lstrip(".")
        if not extension:
            raise ValueError("新扩展名不能为空")
        if INVALID_WINDOWS_CHARS.search(extension) or any(char.isspace() for char in extension):
            raise ValueError("新扩展名不能包含空格或 Windows 文件名非法字符")
        return f".{extension}"

    def preview_organize(self, files: Iterable[Path], root: Path, options: OrganizeOptions) -> list[Action]:
        root = root.resolve()
        if options.mode == "extract":
            if not options.extract_pattern:
                raise ValueError("请填写提取用的正则表达式")
            regex = re.compile(options.extract_pattern)
            group: int | str = int(options.extract_group) if options.extract_group.isdigit() else options.extract_group
            if isinstance(group, int) and group > regex.groups:
                raise ValueError(f"正则表达式只有 {regex.groups} 个捕获组，无法使用第 {group} 组")
            if isinstance(group, str) and group not in regex.groupindex:
                raise ValueError(f"正则表达式中不存在名为 {group!r} 的捕获组")
        actions: list[Action] = []
        reserved: set[str] = set()
        for source in files:
            category = self._category_for(source, options)
            if category is None:
                continue
            folder = root / sanitize_component(category)
            destination = unique_path(folder / source.name, reserved)
            reserved.add(_reserved_key(destination))
            if source.parent != folder:
                actions.append(Action("move", source, destination))
        return actions

    def find_duplicates(
        self,
        files: Iterable[FileEntry] | Iterable[Path],
        options: DuplicateOptions,
        progress=None,
        cancelled=None,
    ) -> DuplicateResult:
        items = list(files)
        if items and all(isinstance(item, FileEntry) for item in items):
            entries: list[tuple[Path, int, float]] = []
            for item in items:
                if item.size is None or item.mtime is None:
                    try:
                        info = item.path.stat()
                    except OSError:
                        continue
                    entries.append((item.path, info.st_size, info.st_mtime))
                else:
                    entries.append((item.path, item.size, item.mtime))
            return find_duplicates_entries(entries, options, progress=progress, cancelled=cancelled)
        return find_duplicates_paths(items, options, progress=progress, cancelled=cancelled)

    def preview_duplicate_cleanup(self, groups: Iterable[DuplicateGroup], root: Path, options: CleanupOptions) -> list[Action]:
        """把每组“保留”以外的文件规划为移动到 根目录/重复文件/组N/ 的 Action。"""
        root = root.resolve()
        folder = root / sanitize_component(options.folder_name)
        selected = sorted(
            (group for group in groups if group.kind in options.kinds),
            key=lambda group: KIND_ORDER.get(group.kind, 99),
        )
        actions: list[Action] = []
        reserved: set[str] = set()
        moved: set[Path] = set()
        kept: set[Path] = set()
        for index, group in enumerate(selected, 1):
            ordered = order_group_members(group.members, options.keeper, group.mtime_of)
            keeper = ordered[0] if ordered else None
            for source in ordered[1:]:
                if source in moved or source in kept or source == keeper:
                    continue
                if is_inside(source, folder):
                    continue
                moved.add(source)
                destination_dir = folder / f"组{index:03d}" if options.group_subfolders else folder
                destination = unique_path(destination_dir / source.name, reserved)
                reserved.add(_reserved_key(destination))
                actions.append(Action("move", source, destination))
            if keeper is not None:
                kept.add(keeper)
        return actions

    def execute(self, actions: Iterable[Action], log_dir: Path) -> tuple[list[Action], Path | None]:
        completed: list[Action] = []
        log_path: Path | None = None
        log_handle = None
        try:
            for action in actions:
                try:
                    if not action.source.exists():
                        raise FileNotFoundError("源文件不存在")
                    # 预览到执行之间目标可能被新建；shutil.move 的回退实现会覆盖它，必须提前拒绝。
                    if action.destination.exists():
                        raise FileExistsError("目标位置已存在同名文件，已跳过以避免覆盖")
                    action.destination.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(action.source), str(action.destination))
                    result = Action(action.operation, action.source, action.destination, ActionStatus.SUCCESS)
                    if log_handle is None:
                        log_dir.mkdir(parents=True, exist_ok=True)
                        stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
                        log_path = log_dir / f"operation_{stamp}.jsonl"
                        log_handle = log_path.open("a", encoding="utf-8")
                    record = {
                        "operation": action.operation,
                        "source": str(action.source),
                        "destination": str(action.destination),
                        "status": str(result.status),
                    }
                    log_handle.write(json.dumps(record, ensure_ascii=False) + "\n")
                    log_handle.flush()
                except Exception as exc:  # keep processing independent items
                    result = Action(action.operation, action.source, action.destination, ActionStatus.FAILED, str(exc))
                completed.append(result)
        finally:
            if log_handle is not None:
                log_handle.close()
        return completed, log_path

    def undo(self, log_path: Path) -> list[Action]:
        try:
            records = self._read_log(log_path)
        except ValueError as exc:
            raise ValueError(f"无法读取日志 {log_path.name}：{exc}") from exc
        # 日志所在目录的上一级即工作目录；撤销只允许操作这棵目录树内的路径。
        allowed_root = log_path.parent.parent
        results: list[Action] = []
        for record in reversed(records):
            current = Path(record["destination"])
            original = Path(record["source"])
            try:
                if not is_inside(current, allowed_root) or not is_inside(original, allowed_root):
                    raise PermissionError("日志中的路径不在日志所在的工作目录内，已拒绝撤销")
                if not current.exists():
                    raise FileNotFoundError("已找不到操作后的文件")
                original.parent.mkdir(parents=True, exist_ok=True)
                if original.exists():
                    raise FileExistsError("原位置已有同名文件")
                shutil.move(str(current), str(original))
                results.append(Action(record["operation"], current, original, ActionStatus.UNDONE))
            except Exception as exc:
                results.append(Action(record["operation"], current, original, ActionStatus.FAILED, str(exc)))
        return results

    @staticmethod
    def _read_log(log_path: Path) -> list[dict[str, str]]:
        """读取日志：支持新的 JSONL 格式和旧版 JSON 数组格式。

        JSONL schema：``{"operation": "rename"|"move", "source": "...",
        "destination": "...", "status": "成功"}``。旧日志可能没有 ``status``，
        读取时忽略该字段；失败条目不写入日志，因此撤销只针对成功操作。
        """
        try:
            text = log_path.read_text(encoding="utf-8")
        except OSError as exc:
            raise ValueError("日志文件无法读取") from exc
        stripped = text.strip()
        if not stripped:
            raise ValueError("日志文件为空")
        records: list[dict] = []
        if stripped.startswith("["):
            try:
                data = json.loads(stripped)
            except json.JSONDecodeError as exc:
                raise ValueError("日志内容不是有效的 JSON") from exc
            if not isinstance(data, list):
                raise ValueError("日志内容不是记录列表")
            records = data
        else:
            for line_number, line in enumerate(stripped.splitlines(), 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError as exc:
                    raise ValueError(f"第 {line_number} 行不是有效的 JSON") from exc
        validated: list[dict[str, str]] = []
        for index, record in enumerate(records, 1):
            if not isinstance(record, dict) or "source" not in record or "destination" not in record:
                raise ValueError(f"第 {index} 条记录缺少 source 或 destination 字段")
            validated.append(
                {
                    "operation": str(record.get("operation", "move")),
                    "source": str(record["source"]),
                    "destination": str(record["destination"]),
                }
            )
        if not validated:
            raise ValueError("日志中没有可撤销的记录")
        return validated

    @staticmethod
    def _category_for(path: Path, options: OrganizeOptions) -> str | None:
        suffix = path.suffix.lower()
        if options.mode == "extension":
            return suffix[1:].upper() if suffix else "无扩展名"
        if options.mode == "type":
            for group, extensions in TYPE_GROUPS.items():
                if suffix in extensions:
                    return group
            return "其他" if options.include_other else None
        if options.mode == "name":
            lowered = path.stem.casefold()
            for keyword, folder in options.name_rules:
                if keyword.casefold() in lowered:
                    return folder
            return "其他" if options.include_other else None
        if options.mode == "extract":
            match = re.search(options.extract_pattern, path.stem)
            if not match:
                return "其他" if options.include_other else None
            group: int | str = int(options.extract_group) if options.extract_group.isdigit() else options.extract_group
            extracted = match.group(group)
            return extracted.strip() if extracted and extracted.strip() else ("其他" if options.include_other else None)
        stat = path.stat()
        if options.mode == "date":
            return datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m")
        size = stat.st_size
        if size < 1 * 1024 * 1024:
            return "小于1MB"
        if size < 100 * 1024 * 1024:
            return "1MB-100MB"
        if size < 1024 * 1024 * 1024:
            return "100MB-1GB"
        return "大于1GB"


def is_inside(path: Path, folder: Path) -> bool:
    """判断文件是否已经位于某个目录内（用于避免重复搬动/越界撤销）。"""
    try:
        return folder.resolve() in path.resolve().parents
    except OSError:
        return folder in path.parents
