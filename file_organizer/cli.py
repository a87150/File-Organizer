from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .core import TYPE_GROUPS, OrganizerEngine, SearchOptions
from .duplicates import DuplicateGroup, DuplicateOptions
from .utils import format_size, normalize_extension


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m file_organizer.cli",
        description="在目录（含子目录）中查找重复或相似文件：文件名相似 / 同格式大小接近 / 字节完全相同",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("root", help="要扫描的目录")
    parser.add_argument("--ext", nargs="*", default=None, help="只处理这些扩展名，默认常见视频格式")
    parser.add_argument("--min-size", type=int, default=1_000_000, help="忽略小于该字节数的文件，默认 1MB")
    parser.add_argument("--max-size", type=int, default=0, help="忽略大于该字节数的文件，0=不限")
    parser.add_argument("--name-thresh", type=float, default=0.75, help="文件名相似度阈值 0~1，默认 0.75")
    parser.add_argument("--no-name", action="store_true", help="跳过文件名比较")
    parser.add_argument("--size-percent", type=float, default=0.0, help="允许大小差异百分比，默认 0（只找完全相同大小）")
    parser.add_argument("--size-diff", type=int, default=0, help="允许大小差异字节数，默认 0")
    parser.add_argument("--no-size", action="store_true", help="跳过按大小找候选")
    parser.add_argument("--hash", action="store_true", help="对同大小候选计算哈希，确认是否字节完全相同")
    parser.add_argument("--workers", type=int, default=4, help="哈希阶段并行读盘线程数，默认 4")
    parser.add_argument("--skip-hidden", action="store_true", help="跳过隐藏文件和目录")
    parser.add_argument("--json", metavar="FILE", help="把结果写入 JSON 文件")
    return parser


def _normalize_extensions(values: list[str]) -> set[str]:
    return {normalize_extension(value) for value in values}


def _rel(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def _print_groups(title: str, groups: list[DuplicateGroup], root: Path, show_size: bool) -> None:
    print()
    print("=" * 78)
    print(f" {title} —— 共 {len(groups)} 组")
    print("=" * 78)
    if not groups:
        print("  （无）")
        return
    for index, group in enumerate(groups, 1):
        print(f"\n[{index}] {len(group.members)} 个文件")
        for path, size in zip(group.members, group.sizes):
            info = f"  ({format_size(size)})" if show_size else ""
            print(f"    {_rel(path, root)}{info}")


def _to_relatives(groups: list[DuplicateGroup], root: Path) -> list[list[str]]:
    return [[_rel(path, root) for path in group.members] for group in groups]


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if not 0 < args.name_thresh <= 1:
        parser.error("--name-thresh 相似度阈值应在 0 到 1 之间")
    if args.size_percent < 0:
        parser.error("--size-percent 大小差异百分比不能为负数")
    if args.size_diff < 0:
        parser.error("--size-diff 大小差异字节数不能为负数")
    if not 1 <= args.workers <= 32:
        parser.error("--workers 读盘线程应在 1 到 32 之间")

    root = Path(args.root).expanduser()
    try:
        root = root.resolve()
    except OSError:
        pass
    if not root.is_dir():
        print(f"错误: {root} 不是有效目录", file=sys.stderr)
        return 1

    extensions = _normalize_extensions(args.ext) if args.ext else set(TYPE_GROUPS["视频"])

    engine = OrganizerEngine()
    try:
        files = engine.scan(root, recursive=True, include_hidden=not args.skip_hidden)
    except ValueError as exc:
        print(f"错误: {exc}", file=sys.stderr)
        return 1

    megabyte = 1024 * 1024
    files = engine.filter_files(
        files,
        SearchOptions(
            extensions=tuple(sorted(extensions)),
            min_size_mb=args.min_size / megabyte,
            max_size_mb=(args.max_size / megabyte) if args.max_size else None,
        ),
    )
    if not files:
        print("没有找到符合条件的文件。")
        return 0

    print(f"扫描目录: {root}")
    print(f"文件数量: {len(files)} 个")
    print(f"格式集合: {', '.join(sorted(extensions))}")

    options = DuplicateOptions(
        name_enabled=not args.no_name,
        name_threshold=args.name_thresh,
        size_enabled=not args.no_size,
        size_tolerance_percent=args.size_percent,
        size_tolerance_bytes=args.size_diff,
        hash_enabled=args.hash,
        workers=args.workers,
    )

    last_stage = ""

    def report_progress(label: str, _value: int, _total: int) -> None:
        nonlocal last_stage
        if label != last_stage:
            last_stage = label
            print(f"{label} ...", file=sys.stderr)

    result = engine.find_duplicates(files, options, progress=report_progress)

    name_groups = [group for group in result.groups if group.kind == "name"]
    size_groups = [group for group in result.groups if group.kind == "size"]
    hash_groups = [group for group in result.groups if group.kind == "hash"]

    payload = {
        "root": str(root),
        "file_count": len(files),
        "name_groups": _to_relatives(name_groups, root),
        "size_groups": _to_relatives(size_groups, root),
        "hash_groups": _to_relatives(hash_groups, root),
    }

    if not args.no_name:
        _print_groups("文件名相似", name_groups, root, show_size=False)
    if not args.no_size:
        _print_groups("同格式 + 大小接近（候选）", size_groups, root, show_size=True)
    if args.hash:
        _print_groups("字节完全相同（哈希确认）", hash_groups, root, show_size=True)

    if args.json:
        try:
            Path(args.json).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"\n结果已写入: {args.json}")
        except OSError as exc:
            print(f"写入 JSON 失败: {exc}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
