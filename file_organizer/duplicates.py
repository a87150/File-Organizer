from __future__ import annotations

import hashlib
import re
import time
from collections import defaultdict
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Callable, Iterable, Literal

DuplicateKind = Literal["name", "size", "hash"]
ProgressCallback = Callable[[str, int, int], None]
CancelCheck = Callable[[], bool]

DEFAULT_HASH_CHUNK = 4 * 1024 * 1024
PREFIX_HASH_BYTES = 4 * 1024 * 1024
PROGRESS_INTERVAL_SECONDS = 0.1

KIND_ORDER: dict[str, int] = {"hash": 0, "size": 1, "name": 2}


class OperationCancelled(Exception):
    """用户在长时间操作中点击了取消。"""


# 常见“副本”后缀，用于名称归一化；copy 前加字母/数字边界，避免撕裂 photocopy 之类的单词。
_COPY_SUFFIX_RE = re.compile(
    r"(?i)(?:\s*[-_ ]?\s*(?<![a-z0-9])(?:副本|拷贝|复件|copy)(?:\s*\(?\d+\)?)?"
    r"|\s*\(\s*\d+\s*\)"
    r"|\s+-\s+\d+"
    r")$"
)


class DSU:
    """并查集，用来把两两相似/接近的文件合并成组。"""

    def __init__(self, items: Iterable[Path] = ()) -> None:
        self.p: dict[Path, Path] = {item: item for item in items}

    def find(self, x: Path) -> Path:
        p = self.p
        p.setdefault(x, x)
        root = x
        while p[root] != root:
            root = p[root]
        while p[x] != root:
            p[x], x = root, p[x]
        return root

    def union(self, a: Path, b: Path) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.p[rb] = ra

    def groups(self) -> list[list[Path]]:
        buckets: dict[Path, list[Path]] = defaultdict(list)
        for key in list(self.p):
            buckets[self.find(key)].append(key)
        return [sorted(members) for members in buckets.values() if len(members) > 1]


def normalize_stem(path: Path) -> str:
    """去掉扩展名、转小写、剥离常见副本后缀（副本/copy/(1)/ - 1）。"""
    stem = path.stem.lower().strip()
    for _ in range(3):
        stripped = _COPY_SUFFIX_RE.sub("", stem).strip()
        if stripped == stem or not stripped:
            break
        stem = stripped
    return stem


def digest_file(
    path: Path,
    *,
    limit: int | None = None,
    chunk: int = DEFAULT_HASH_CHUNK,
    on_chunk: Callable[[int], None] | None = None,
    cancelled: CancelCheck | None = None,
) -> str:
    """分块计算 BLAKE2b 摘要；limit 限制只读取前 N 字节，用于第一轮预筛。"""
    hasher = hashlib.blake2b(digest_size=16)
    remaining = limit
    with open(path, "rb") as handle:
        while remaining is None or remaining > 0:
            if cancelled is not None and cancelled():
                raise OperationCancelled
            read_size = chunk if remaining is None else min(chunk, remaining)
            block = handle.read(read_size)
            if not block:
                break
            hasher.update(block)
            if remaining is not None:
                remaining -= len(block)
            if on_chunk is not None:
                on_chunk(len(block))
    return hasher.hexdigest()


class _ProgressMeter:
    """按字节累计进度，并做频率限制，避免向 UI 发送过多事件。"""

    def __init__(self, label: str, total: int, callback: ProgressCallback | None) -> None:
        self.label = label
        self.total = max(int(total), 1)
        self.callback = callback
        self.done = 0
        self.last_emit = 0.0

    def add(self, amount: int) -> None:
        self.done += amount
        if self.callback is None:
            return
        now = time.monotonic()
        if now - self.last_emit >= PROGRESS_INTERVAL_SECONDS:
            self.last_emit = now
            self.callback(self.label, min(self.done, self.total), self.total)

    def finish(self) -> None:
        if self.callback is not None:
            self.callback(self.label, self.total, self.total)


@dataclass(frozen=True)
class DuplicateOptions:
    name_enabled: bool = True
    name_threshold: float = 0.75
    size_enabled: bool = True
    size_tolerance_percent: float = 0.0
    size_tolerance_bytes: int = 0
    hash_enabled: bool = False


@dataclass(frozen=True)
class DuplicateGroup:
    kind: DuplicateKind
    members: tuple[Path, ...]
    sizes: tuple[int, ...]

    @property
    def count(self) -> int:
        return len(self.members)

    @property
    def total_size(self) -> int:
        return sum(self.sizes)

    @property
    def reclaimable_bytes(self) -> int:
        """按保留一个、其余移走估算可释放空间（近似值）。"""
        if len(self.sizes) < 2:
            return 0
        return self.total_size - max(self.sizes)


@dataclass(frozen=True)
class DuplicateResult:
    groups: tuple[DuplicateGroup, ...]
    files_scanned: int
    hashed_files: int
    hashed_bytes: int
    elapsed: float


def order_group_members(members: tuple[Path, ...], keeper: str) -> list[Path]:
    """按保留规则排序组内文件，第一个成员是建议保留的文件。"""
    if keeper == "first":
        return sorted(members, key=lambda path: str(path).casefold())
    if keeper in ("oldest", "newest"):
        fallback = float("inf") if keeper == "oldest" else float("-inf")

        def mtime_key(path: Path) -> tuple:
            try:
                mtime = path.stat().st_mtime
            except OSError:
                mtime = fallback
            if keeper == "newest":
                mtime = -mtime
            return (mtime, str(path).casefold())

        return sorted(members, key=mtime_key)
    # shortest-path：路径层级最少、字符串最短的排前面
    return sorted(members, key=lambda path: (len(path.parts), len(str(path)), str(path).casefold()))


def find_name_groups(
    paths: Iterable[Path],
    threshold: float,
    progress: ProgressCallback | None = None,
    cancelled: CancelCheck | None = None,
) -> list[list[Path]]:
    """按归一化文件名的相似度分组，使用 SequenceMatcher + 长度上界剪枝。"""
    items = sorted(((path, normalize_stem(path)) for path in paths), key=lambda item: len(item[1]))
    total = len(items)
    dsu = DSU(path for path, _ in items)
    for i, (path_i, stem_i) in enumerate(items):
        if cancelled is not None and i % 256 == 0 and cancelled():
            raise OperationCancelled
        for j in range(i + 1, total):
            stem_j = items[j][1]
            combined = len(stem_i) + len(stem_j)
            # ratio 上界为 2*min/(a+b)，低于阈值时后续项更不可能匹配，直接截断
            if combined == 0 or 2 * len(stem_i) / combined < threshold:
                break
            matcher = SequenceMatcher(None, stem_i, stem_j)
            if matcher.real_quick_ratio() < threshold:
                continue
            if matcher.quick_ratio() < threshold:
                continue
            if matcher.ratio() >= threshold:
                dsu.union(path_i, items[j][0])
        if progress is not None and (i % 64 == 0 or i == total - 1):
            progress("正在比较文件名", i + 1, max(total, 1))
    return dsu.groups()


def find_size_groups(
    entries: Iterable[tuple[Path, int, str]],
    tolerance_percent: float,
    tolerance_bytes: int,
    progress: ProgressCallback | None = None,
    cancelled: CancelCheck | None = None,
) -> list[list[Path]]:
    """按扩展名分组后查找大小接近的候选（容差内相邻项并查集合并）。"""
    by_extension: dict[str, list[tuple[Path, int]]] = defaultdict(list)
    for path, size, extension in entries:
        by_extension[extension].append((path, size))
    extensions = sorted(by_extension)
    results: list[list[Path]] = []
    for index, extension in enumerate(extensions, 1):
        items = sorted(by_extension[extension], key=lambda item: (item[1], str(item[0]).casefold()))
        total = len(items)
        dsu = DSU(path for path, _ in items)
        for i in range(total):
            path_i, size_i = items[i]
            if cancelled is not None and i % 256 == 0 and cancelled():
                raise OperationCancelled
            allowed = size_i + max(tolerance_bytes, size_i * tolerance_percent / 100.0)
            for j in range(i + 1, total):
                path_j, size_j = items[j]
                if size_j <= allowed:
                    dsu.union(path_i, path_j)
                else:
                    break
        results.extend(dsu.groups())
        if progress is not None:
            progress("正在按大小分组", index, max(len(extensions), 1))
    return results


def confirm_hash_groups(
    entries: Iterable[tuple[Path, int, str]],
    progress: ProgressCallback | None = None,
    cancelled: CancelCheck | None = None,
) -> tuple[list[list[Path]], int, int]:
    """按精确大小分桶 → 前缀哈希预筛 → 全量哈希确认字节完全相同。

    返回 (分组列表, 参与哈希的文件数, 实际读取的字节数)。
    """
    by_size: dict[int, list[Path]] = defaultdict(list)
    for path, size, _extension in entries:
        by_size[size].append(path)
    planned = sum(size * len(paths) for size, paths in by_size.items() if len(paths) > 1)
    hashed_files = sum(len(paths) for paths in by_size.values() if len(paths) > 1)
    if hashed_files == 0:
        return [], 0, 0

    meter = _ProgressMeter("正在计算哈希", planned, progress)

    def on_chunk(amount: int) -> None:
        meter.add(amount)

    confirmed: list[list[Path]] = []
    for size, paths in sorted(by_size.items()):
        if len(paths) < 2:
            continue
        paths = sorted(paths, key=lambda path: str(path).casefold())
        prefix_buckets: dict[str, list[Path]] = defaultdict(list)
        for path in paths:
            try:
                digest = digest_file(path, limit=PREFIX_HASH_BYTES, on_chunk=on_chunk, cancelled=cancelled)
            except OSError:
                continue
            prefix_buckets[digest].append(path)
        for bucket in prefix_buckets.values():
            if len(bucket) < 2:
                continue
            if size <= PREFIX_HASH_BYTES:
                confirmed.append(sorted(bucket))
                continue
            full_buckets: dict[str, list[Path]] = defaultdict(list)
            for path in bucket:
                try:
                    digest = digest_file(path, on_chunk=on_chunk, cancelled=cancelled)
                except OSError:
                    continue
                full_buckets[digest].append(path)
            for full_bucket in full_buckets.values():
                if len(full_bucket) > 1:
                    confirmed.append(sorted(full_bucket))
    meter.finish()
    return confirmed, hashed_files, meter.done


def find_duplicates(
    files: Iterable[Path],
    options: DuplicateOptions,
    progress: ProgressCallback | None = None,
    cancelled: CancelCheck | None = None,
) -> DuplicateResult:
    """执行重复/相似文件查找，返回按 hash → size → name 排序的分组结果。"""
    started = time.perf_counter()
    entries: list[tuple[Path, int, str]] = []
    for path in sorted(set(files), key=lambda item: str(item).casefold()):
        try:
            stat = path.stat()
        except OSError:
            continue
        entries.append((path, stat.st_size, path.suffix.casefold()))
    size_of = {path: size for path, size, _ in entries}

    groups: list[DuplicateGroup] = []
    hashed_files = 0
    hashed_bytes = 0

    if options.hash_enabled:
        hash_groups, hashed_files, hashed_bytes = confirm_hash_groups(entries, progress=progress, cancelled=cancelled)
        groups.extend(_make_groups("hash", hash_groups, size_of))
    if options.size_enabled:
        size_groups = find_size_groups(
            entries,
            options.size_tolerance_percent,
            options.size_tolerance_bytes,
            progress=progress,
            cancelled=cancelled,
        )
        groups.extend(_make_groups("size", size_groups, size_of))
    if options.name_enabled:
        name_groups = find_name_groups(
            (path for path, _, _ in entries),
            options.name_threshold,
            progress=progress,
            cancelled=cancelled,
        )
        groups.extend(_make_groups("name", name_groups, size_of))

    return DuplicateResult(
        groups=tuple(groups),
        files_scanned=len(entries),
        hashed_files=hashed_files,
        hashed_bytes=hashed_bytes,
        elapsed=time.perf_counter() - started,
    )


def _make_groups(kind: DuplicateKind, member_lists: Iterable[Iterable[Path]], size_of: dict[Path, int]) -> list[DuplicateGroup]:
    made: list[DuplicateGroup] = []
    for members in member_lists:
        paths = tuple(members)
        made.append(DuplicateGroup(kind, paths, tuple(size_of.get(path, 0) for path in paths)))
    return made
