from __future__ import annotations

import json
import os
import re
import shutil
from dataclasses import dataclass
from datetime import date, datetime, time
from pathlib import Path
from typing import Iterable, Literal

from .duplicates import KIND_ORDER, DuplicateGroup, DuplicateOptions, DuplicateResult, find_duplicates, order_group_members


INVALID_WINDOWS_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')

STATUS_PENDING = "待执行"
STATUS_SUCCESS = "成功"
STATUS_FAILED = "失败"
STATUS_UNDONE = "已撤销"

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
    status: str = STATUS_PENDING
    message: str = ""


def sanitize_component(value: str) -> str:
    value = INVALID_WINDOWS_CHARS.sub("_", value).strip().rstrip(".")
    return value or "未命名"


def unique_path(path: Path, reserved: set[Path] | None = None) -> Path:
    reserved = reserved or set()
    if not path.exists() and path not in reserved:
        return path
    counter = 1
    while True:
        candidate = path.with_name(f"{path.stem} ({counter}){path.suffix}")
        if not candidate.exists() and candidate not in reserved:
            return candidate
        counter += 1


class OrganizerEngine:
    def scan(self, folder: Path, recursive: bool = False, include_hidden: bool = False) -> list[Path]:
        folder = folder.expanduser().resolve()
        if not folder.is_dir():
            raise ValueError(f"文件夹不存在：{folder}")
        files: list[Path] = []
        stack = [folder]
        while stack:
            current = stack.pop()
            try:
                entries = list(os.scandir(current))
            except OSError:
                continue
            for entry in entries:
                name = entry.name
                if not include_hidden and name.startswith("."):
                    continue
                try:
                    if entry.is_dir(follow_symlinks=False):
                        if recursive:
                            stack.append(Path(entry.path))
                        continue
                    if entry.is_file():
                        files.append(Path(entry.path))
                except OSError:
                    continue
        return sorted(files, key=lambda path: str(path).casefold())

    def filter_files(self, files: Iterable[Path], options: SearchOptions) -> list[Path]:
        pattern = re.compile(options.name_pattern, re.IGNORECASE) if options.name_pattern and options.use_regex else None
        extensions: set[str] = set()
        for value in options.extensions:
            cleaned = value.strip()
            extensions.add(cleaned.casefold() if not cleaned or cleaned.startswith(".") else f".{cleaned.casefold()}")
        minimum = options.min_size_mb * 1024 * 1024 if options.min_size_mb is not None else None
        maximum = options.max_size_mb * 1024 * 1024 if options.max_size_mb is not None else None
        modified_from = datetime.combine(options.modified_from, time.min).timestamp() if options.modified_from else None
        modified_to = datetime.combine(options.modified_to, time.max).timestamp() if options.modified_to else None
        matches: list[Path] = []
        for path in files:
            if options.name_pattern:
                name_matches = bool(pattern.search(path.name)) if pattern else options.name_pattern.casefold() in path.name.casefold()
                if not name_matches:
                    continue
            if extensions and path.suffix.casefold() not in extensions:
                continue
            try:
                stat = path.stat()
            except OSError:
                continue
            size = stat.st_size
            if minimum is not None and size < minimum:
                continue
            if maximum is not None and size > maximum:
                continue
            if modified_from is not None and stat.st_mtime < modified_from:
                continue
            if modified_to is not None and stat.st_mtime > modified_to:
                continue
            matches.append(path)
        return matches

    def preview_rename(self, files: Iterable[Path], options: RenameOptions) -> list[Action]:
        actions: list[Action] = []
        reserved: set[Path] = set()
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
            new_stem = sanitize_component(f"{options.prefix}{stem}{options.suffix}{counter}")
            extension = source.suffix
            if options.new_extension.strip():
                extension = self._normalize_extension(options.new_extension)
            destination = unique_path(source.with_name(new_stem + extension), reserved)
            reserved.add(destination)
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
        reserved: set[Path] = set()
        for source in files:
            category = self._category_for(source, options)
            if category is None:
                continue
            folder = root / sanitize_component(category)
            destination = unique_path(folder / source.name, reserved)
            reserved.add(destination)
            if source.parent != folder:
                actions.append(Action("move", source, destination))
        return actions

    def find_duplicates(
        self,
        files: Iterable[Path],
        options: DuplicateOptions,
        progress=None,
        cancelled=None,
    ) -> DuplicateResult:
        return find_duplicates(files, options, progress=progress, cancelled=cancelled)

    def preview_duplicate_cleanup(self, groups: Iterable[DuplicateGroup], root: Path, options: CleanupOptions) -> list[Action]:
        """把每组“保留”以外的文件规划为移动到 根目录/重复文件/组N/ 的 Action。"""
        root = root.resolve()
        folder = root / sanitize_component(options.folder_name)
        selected = sorted(
            (group for group in groups if group.kind in options.kinds),
            key=lambda group: KIND_ORDER.get(group.kind, 99),
        )
        actions: list[Action] = []
        reserved: set[Path] = set()
        moved: set[Path] = set()
        kept: set[Path] = set()
        for index, group in enumerate(selected, 1):
            ordered = order_group_members(group.members, options.keeper)
            keeper = ordered[0] if ordered else None
            for source in ordered[1:]:
                if source in moved or source in kept or source == keeper:
                    continue
                if is_inside(source, folder):
                    continue
                moved.add(source)
                destination_dir = folder / f"组{index:03d}" if options.group_subfolders else folder
                destination = unique_path(destination_dir / source.name, reserved)
                reserved.add(destination)
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
                    action.destination.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(action.source), str(action.destination))
                    result = Action(action.operation, action.source, action.destination, STATUS_SUCCESS)
                    if log_handle is None:
                        log_dir.mkdir(parents=True, exist_ok=True)
                        stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
                        log_path = log_dir / f"operation_{stamp}.jsonl"
                        log_handle = log_path.open("a", encoding="utf-8")
                    record = {"operation": action.operation, "source": str(action.source), "destination": str(action.destination)}
                    log_handle.write(json.dumps(record, ensure_ascii=False) + "\n")
                    log_handle.flush()
                except Exception as exc:  # keep processing independent items
                    result = Action(action.operation, action.source, action.destination, STATUS_FAILED, str(exc))
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
        results: list[Action] = []
        for record in reversed(records):
            current = Path(record["destination"])
            original = Path(record["source"])
            try:
                if not current.exists():
                    raise FileNotFoundError("已找不到操作后的文件")
                original.parent.mkdir(parents=True, exist_ok=True)
                if original.exists():
                    raise FileExistsError("原位置已有同名文件")
                shutil.move(str(current), str(original))
                results.append(Action(record["operation"], current, original, STATUS_UNDONE))
            except Exception as exc:
                results.append(Action(record["operation"], current, original, STATUS_FAILED, str(exc)))
        return results

    @staticmethod
    def _read_log(log_path: Path) -> list[dict[str, str]]:
        """读取日志：支持新的 JSONL 格式和旧版 JSON 数组格式。"""
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
    """判断文件是否已经位于某个目录内（用于避免重复搬动）。"""
    try:
        return folder.resolve() in path.resolve().parents
    except OSError:
        return folder in path.parents
