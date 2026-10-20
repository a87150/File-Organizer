from __future__ import annotations

import hashlib
import re
import threading
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
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
        self._lock = threading.Lock()
        self._callback_lock = threading.Lock()

    def add(self, amount: int) -> None:
        emit: tuple[str, int, int] | None = None
        with self._lock:
            self.done += amount
            if self.callback is not None:
                now = time.monotonic()
                if now - self.last_emit >= PROGRESS_INTERVAL_SECONDS:
                    self.last_emit = now
                    emit = (self.label, min(self.done, self.total), self.total)
        if emit is not None and self.callback is not None:
            with self._callback_lock:
                self.callback(*emit)

    def finish(self) -> None:
        with self._lock:
            self.done = self.total
        if self.callback is not None:
            with self._callback_lock:
                self.callback(self.label, self.total, self.total)


@dataclass(frozen=True)
class DuplicateOptions:
    name_enabled: bool = True
    name_threshold: float = 0.75
    size_enabled: bool = True
    size_tolerance_percent: float = 0.0
    size_tolerance_bytes: int = 0
    hash_enabled: bool = False
    # 哈希阶段并行读盘的线程数；机械硬盘可调小，SSD 可适当调大。
    workers: int = 4


@dataclass(frozen=True)
class DuplicateGroup:
    kind: DuplicateKind
    members: tuple[Path, ...]
    sizes: tuple[int, ...]
    mtime_of: dict[Path, float] = field(default_factory=dict, compare=False, repr=False)

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


def order_group_members(
    members: tuple[Path, ...],
    keeper: str,
    mtime_of: dict[Path, float] | None = None,
) -> list[Path]:
    """按保留规则排序组内文件，第一个成员是建议保留的文件。

    ``mtime_of`` 传入查重阶段缓存的修改时间；缺省时才回退到现场 stat。
    """
    if keeper == "first":
        return sorted(members, key=lambda path: str(path).casefold())
    if keeper in ("oldest", "newest"):
        fallback = float("inf") if keeper == "oldest" else float("-inf")

        def mtime_key(path: Path) -> tuple:
            if mtime_of is not None and path in mtime_of:
                mtime = mtime_of[path]
            else:
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
    """按归一化文件名的相似度分组，使用 SequenceMatcher + 长度上界剪枝。

    优化点：
    1. 归一化名完全相同的文件直接用精确桶合并，不再两两比较；
    2. 已经在同一并查集分组的候选对直接跳过；
    3. 长度排序后的上界剪枝保持不变，结果与原两两算法一致。
    """
    items = sorted(
        ((path, normalize_stem(path)) for path in paths),
        key=lambda item: (len(item[1]), str(item[0]).casefold()),
    )
    dsu = DSU(path for path, _ in items)

    # 精确桶：同名（副本）先合并，只留下每个桶的代表参与相似度比较。
    buckets: dict[str, list[Path]] = defaultdict(list)
    for path, stem in items:
        buckets[stem].append(path)
    representatives: list[tuple[Path, str]] = []
    for stem, members in buckets.items():
        for member in members[1:]:
            dsu.union(members[0], member)
        representatives.append((members[0], stem))
    representatives.sort(key=lambda item: (len(item[1]), str(item[0]).casefold()))

    total = len(representatives)
    for i, (path_i, stem_i) in enumerate(representatives):
        if cancelled is not None and i % 256 == 0 and cancelled():
            raise OperationCancelled
        for j in range(i + 1, total):
            path_j, stem_j = representatives[j]
            combined = len(stem_i) + len(stem_j)
            # ratio 上界为 2*min/(a+b)，低于阈值时后续项更不可能匹配，直接截断
            if combined == 0 or 2 * len(stem_i) / combined < threshold:
                break
            if dsu.find(path_i) == dsu.find(path_j):
                continue
            matcher = SequenceMatcher(None, stem_i, stem_j)
            if matcher.real_quick_ratio() < threshold:
                continue
            if matcher.quick_ratio() < threshold:
                continue
            if matcher.ratio() >= threshold:
                dsu.union(path_i, path_j)
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


def _digest_many(
    paths: list[Path],
    *,
    limit: int | None,
    meter: _ProgressMeter,
    workers: int,
    cancelled: CancelCheck | None,
) -> dict[Path, str]:
    """并行计算一组文件的摘要；取消时让异常自然向上传播。"""

    def work(path: Path) -> str:
        return digest_file(path, limit=limit, on_chunk=meter.add, cancelled=cancelled)

    results: dict[Path, str] = {}
    if workers <= 1:
        for path in paths:
            try:
                results[path] = work(path)
            except OSError:
                continue
        return results

    executor = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="hash")
    try:
        futures = {executor.submit(work, path): path for path in paths}
        for future in as_completed(futures):
            path = futures[future]
            try:
                results[path] = future.result()
            except OSError:
                continue
    except BaseException:
        # 取消或其它异常：尽快停掉尚未开始的读取任务，已运行的任务会检查取消信号。
        executor.shutdown(wait=False, cancel_futures=True)
        raise
    else:
        executor.shutdown(wait=True)
        return results


def confirm_hash_groups(
    entries: Iterable[tuple[Path, int, str]],
    progress: ProgressCallback | None = None,
    cancelled: CancelCheck | None = None,
    workers: int = 4,
) -> tuple[list[list[Path]], int, int]:
    """按精确大小分桶 → 前缀哈希预筛 → 全量哈希确认字节完全相同。

    同大小桶内使用线程池并行读盘；进度回调由 ``_ProgressMeter`` 加锁合并。
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
    worker_count = max(1, int(workers))

    confirmed: list[list[Path]] = []
    for size, paths in sorted(by_size.items()):
        if len(paths) < 2:
            continue
        paths = sorted(paths, key=lambda path: str(path).casefold())
        prefix_buckets: dict[str, list[Path]] = defaultdict(list)
        for path, digest in _digest_many(
            paths,
            limit=PREFIX_HASH_BYTES,
            meter=meter,
            workers=worker_count,
            cancelled=cancelled,
        ).items():
            prefix_buckets[digest].append(path)
        for bucket in prefix_buckets.values():
            if len(bucket) < 2:
                continue
            if size <= PREFIX_HASH_BYTES:
                confirmed.append(sorted(bucket))
                continue
            full_buckets: dict[str, list[Path]] = defaultdict(list)
            for path, digest in _digest_many(
                sorted(bucket),
                limit=None,
                meter=meter,
                workers=worker_count,
                cancelled=cancelled,
            ).items():
                full_buckets[digest].append(path)
            for full_bucket in full_buckets.values():
                if len(full_bucket) > 1:
                    confirmed.append(sorted(full_bucket))
    meter.finish()
    confirmed.sort(key=lambda members: str(members[0]).casefold())
    return confirmed, hashed_files, meter.done


def _trim_size_diameter(
    groups: Iterable[Iterable[Path]],
    size_of: dict[Path, int],
    tolerance_percent: float,
    tolerance_bytes: int,
) -> list[list[Path]]:
    """按“组内最大最小之差不超过容差”再细分一次。

    链式合并（a≈b、b≈c）会把 a 和 c 并到一组，这里保证同一组里任意两个文件的
    大小差距都在容差范围内。
    """
    result: list[list[Path]] = []
    for members in groups:
        ordered = sorted(members, key=lambda path: (size_of.get(path, 0), str(path).casefold()))
        chunk: list[Path] = []
        limit = 0.0
        for path in ordered:
            size = size_of.get(path, 0)
            if chunk and size > limit:
                if len(chunk) > 1:
                    result.append(chunk)
                chunk = []
            if not chunk:
                limit = size + max(tolerance_bytes, size * tolerance_percent / 100.0)
            chunk.append(path)
        if len(chunk) > 1:
            result.append(chunk)
    return result


def find_duplicates_entries(
    entries: Iterable[tuple[Path, int, float]],
    options: DuplicateOptions,
    progress: ProgressCallback | None = None,
    cancelled: CancelCheck | None = None,
) -> DuplicateResult:
    """用扫描阶段缓存的 (path, size, mtime) 查重，避免重复 stat。"""
    started = time.perf_counter()
    normalized: list[tuple[Path, int, float, str]] = []
    seen: set[Path] = set()
    for path, size, mtime in sorted(entries, key=lambda item: str(item[0]).casefold()):
        if path in seen:
            continue
        seen.add(path)
        normalized.append((path, int(size), float(mtime), path.suffix.casefold()))

    size_of = {path: size for path, size, _mtime, _extension in normalized}
    mtime_of = {path: mtime for path, _size, mtime, _extension in normalized}
    extension_of = {path: extension for path, _size, _mtime, extension in normalized}
    hash_entries = [(path, size, extension) for path, size, _mtime, extension in normalized]

    groups: list[list[Path]] = []
    hashed_files = 0
    hashed_bytes = 0
    refined: set[str] = set()

    if options.hash_enabled:
        # 内容完全相同 ⇒ 大小必然相同，哈希优先时无需再按大小细分。
        confirmed, hashed_files, hashed_bytes = confirm_hash_groups(
            hash_entries,
            progress=progress,
            cancelled=cancelled,
            workers=options.workers,
        )
        groups = [list(members) for members in confirmed]
        refined.update(("hash", "size"))
    elif options.size_enabled:
        groups = find_size_groups(
            hash_entries,
            options.size_tolerance_percent,
            options.size_tolerance_bytes,
            progress=progress,
            cancelled=cancelled,
        )
        refined.add("size")
    elif options.name_enabled:
        groups = find_name_groups(
            (path for path, _size, _mtime, _extension in normalized),
            options.name_threshold,
            progress=progress,
            cancelled=cancelled,
        )
        refined.add("name")

    if options.size_enabled and "size" not in refined:
        groups = [
            chunk
            for members in groups
            for chunk in find_size_groups(
                [(path, size_of.get(path, 0), extension_of.get(path, "")) for path in members],
                options.size_tolerance_percent,
                options.size_tolerance_bytes,
                cancelled=cancelled,
            )
        ]
    if options.name_enabled and "name" not in refined:
        groups = [
            chunk
            for members in groups
            for chunk in find_name_groups(members, options.name_threshold, cancelled=cancelled)
        ]
    if options.size_enabled:
        groups = _trim_size_diameter(groups, size_of, options.size_tolerance_percent, options.size_tolerance_bytes)

    kind: DuplicateKind = "hash" if options.hash_enabled else ("name" if options.name_enabled else "size")
    made = [
        DuplicateGroup(
            kind,
            tuple(members),
            tuple(size_of.get(path, 0) for path in members),
            {path: mtime_of[path] for path in members if path in mtime_of},
        )
        for members in groups
        if len(members) > 1
    ]

    return DuplicateResult(
        groups=tuple(made),
        files_scanned=len(normalized),
        hashed_files=hashed_files,
        hashed_bytes=hashed_bytes,
        elapsed=time.perf_counter() - started,
    )


def find_duplicates(
    files: Iterable[Path],
    options: DuplicateOptions,
    progress: ProgressCallback | None = None,
    cancelled: CancelCheck | None = None,
) -> DuplicateResult:
    """执行重复/相似文件查找（路径入口，兼容 CLI 与外部调用）。

    勾选的多项查找方式会叠加生效：先用最可靠的一项初筛，再用其余条件逐层细分，
    只保留仍有两个及以上成员的分组。例如同时勾选“文件名相似”和“大小接近”时，
    组内文件必须名字相似，且大小差距也在容差范围内。
    """
    entries: list[tuple[Path, int, float]] = []
    for path in sorted(set(files), key=lambda item: str(item).casefold()):
        try:
            stat = path.stat()
        except OSError:
            continue
        entries.append((path, stat.st_size, stat.st_mtime))
    return find_duplicates_entries(entries, options, progress=progress, cancelled=cancelled)
