import contextlib
import io
import json
import os
import tempfile
import unittest
from difflib import SequenceMatcher
from pathlib import Path
from unittest import mock

from file_organizer import cli
from file_organizer.core import CleanupOptions, FileEntry, OrganizerEngine
from file_organizer.duplicates import (
    DSU,
    DuplicateGroup,
    DuplicateOptions,
    find_name_groups,
    find_size_groups,
    normalize_stem,
    order_group_members,
)


class DuplicateFinderTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.engine = OrganizerEngine()

    def tearDown(self):
        self.temp.cleanup()

    def make_file(self, name: str, content: bytes = b"x") -> Path:
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return path

    def test_exact_duplicates_confirmed_by_hash(self):
        first = self.make_file("movie_a.mp4", b"x" * 4096 + b"tail")
        second = self.make_file("movie_b.mp4", b"x" * 4096 + b"tail")
        different = self.make_file("movie_c.mp4", b"y" * 4100)
        self.assertEqual(first.stat().st_size, different.stat().st_size)
        result = self.engine.find_duplicates(
            [first, second, different],
            DuplicateOptions(name_enabled=False, size_enabled=False, hash_enabled=True),
        )
        hash_groups = [group for group in result.groups if group.kind == "hash"]
        self.assertEqual(len(hash_groups), 1)
        self.assertEqual(set(hash_groups[0].members), {first, second})
        self.assertEqual(result.hashed_files, 3)
        self.assertEqual(result.hashed_bytes, 4100 * 3)

    def test_hash_without_size_step_finds_duplicates(self):
        # 回归：旧 s.py 在 --no-size --hash 组合下会静默跳过哈希阶段
        first = self.make_file("dup1.bin", b"abcdef")
        second = self.make_file("dup2.bin", b"abcdef")
        result = self.engine.find_duplicates(
            [first, second],
            DuplicateOptions(name_enabled=False, size_enabled=False, hash_enabled=True),
        )
        self.assertEqual(len(result.groups), 1)
        self.assertEqual(result.groups[0].kind, "hash")
        self.assertEqual(set(result.groups[0].members), {first, second})

    def test_name_groups_normalize_copy_suffix(self):
        base = self.make_file("电影.mkv", b"1")
        copy = self.make_file("电影 - 副本.mkv", b"2")
        self.make_file("剧场版.mkv", b"3")
        result = self.engine.find_duplicates(
            [base, copy, self.root / "剧场版.mkv"],
            DuplicateOptions(name_threshold=0.75, size_enabled=False, hash_enabled=False),
        )
        name_groups = [group for group in result.groups if group.kind == "name"]
        self.assertEqual(len(name_groups), 1)
        self.assertEqual(set(name_groups[0].members), {base, copy})

    def test_normalize_stem_boundaries(self):
        self.assertEqual(normalize_stem(Path("photocopy.mp4")), "photocopy")
        self.assertEqual(normalize_stem(Path("movie_copy2.mp4")), "movie")
        self.assertEqual(normalize_stem(Path("backup copy.mp4")), "backup")
        self.assertEqual(normalize_stem(Path("video (1).mp4")), "video")

    def test_name_threshold_boundary(self):
        first = self.make_file("abcdefgh.mp4", b"1")
        second = self.make_file("abcdxxxx.mp4", b"2")
        below = self.engine.find_duplicates(
            [first, second],
            DuplicateOptions(name_threshold=0.6, size_enabled=False, hash_enabled=False),
        )
        self.assertEqual(below.groups, ())
        above = self.engine.find_duplicates(
            [first, second],
            DuplicateOptions(name_threshold=0.4, size_enabled=False, hash_enabled=False),
        )
        self.assertEqual(len(above.groups), 1)

    def test_size_groups_chain_semantics(self):
        entries = [(Path("a.bin"), 100, ".bin"), (Path("b.bin"), 105, ".bin"), (Path("c.bin"), 111, ".bin")]
        chained = find_size_groups(entries, 0.0, 10)
        self.assertEqual(len(chained), 1)
        self.assertEqual(len(chained[0]), 3)
        separate = find_size_groups(entries, 0.0, 4)
        self.assertEqual(separate, [])

    def test_name_and_size_stack(self):
        # 叠加：同时勾选“文件名相似”和“大小接近”时，大小差距大的文件不再成组
        first = self.make_file("song_a.mp3", b"a" * 1000)
        big = self.make_file("song_b.mp3", b"b" * 4000)
        peer = self.make_file("song_c.mp3", b"c" * 1000)
        result = self.engine.find_duplicates([first, big, peer], DuplicateOptions(name_threshold=0.75))
        self.assertEqual(len(result.groups), 1)
        self.assertEqual(set(result.groups[0].members), {first, peer})

    def test_mixed_file_entries_and_paths(self):
        # 回归：FileEntry 与 Path 混用时不能落入只接受 Path 的旧回退分支。
        first = self.make_file("mixed_a.bin", b"same")
        second = self.make_file("mixed_b.bin", b"same")
        info = second.stat()
        mixed = [first, FileEntry(second, info.st_size, info.st_mtime)]
        result = self.engine.find_duplicates(
            mixed,
            DuplicateOptions(name_enabled=False, size_enabled=True, hash_enabled=False),
        )
        self.assertEqual(result.files_scanned, 2)
        self.assertEqual(len(result.groups), 1)
        self.assertEqual(set(result.groups[0].members), {first, second})

    def test_size_diameter_trim(self):
        # 链式合并（100≈105≈111）不应把大小差距超过容差的文件并进同一组
        first = self.make_file("t1.bin", b"a" * 100)
        second = self.make_file("t2.bin", b"b" * 105)
        third = self.make_file("t3.bin", b"c" * 111)
        result = self.engine.find_duplicates(
            [first, second, third],
            DuplicateOptions(name_enabled=False, size_enabled=True, hash_enabled=False, size_tolerance_bytes=10),
        )
        groups = {frozenset(group.members) for group in result.groups}
        self.assertEqual(groups, {frozenset({first, second})})

    def test_cleanup_keeper_oldest(self):
        old = self.make_file("dup_old.bin", b"same")
        new_first = self.make_file("dup_new1.bin", b"same")
        new_second = self.make_file("dup_new2.bin", b"same")
        os.utime(old, (1000, 1000))
        os.utime(new_first, (2000, 2000))
        os.utime(new_second, (3000, 3000))
        size = old.stat().st_size
        group = DuplicateGroup("hash", (old, new_first, new_second), (size, size, size))
        actions = self.engine.preview_duplicate_cleanup([group], self.root, CleanupOptions(kinds=("hash",), keeper="oldest"))
        sources = {action.source for action in actions}
        self.assertNotIn(old, sources)
        self.assertEqual(sources, {new_first, new_second})
        for action in actions:
            self.assertEqual(action.destination.parent, self.root / "重复文件" / "组001")

    def test_cleanup_skips_members_already_inside_folder(self):
        inside = self.make_file("重复文件/组001/already.bin", b"same")
        outside = self.make_file("outside.bin", b"same")
        size = outside.stat().st_size
        group = DuplicateGroup("hash", (inside, outside), (size, size))
        actions = self.engine.preview_duplicate_cleanup([group], self.root, CleanupOptions(kinds=("hash",), keeper="shortest-path"))
        self.assertEqual(actions, [])

    def test_cleanup_deduplicates_across_kinds(self):
        first = self.make_file("photo1.bin", b"12345")
        second = self.make_file("photo2.bin", b"12345")
        third = self.make_file("other.bin", b"xxxxx")
        size = first.stat().st_size
        name_group = DuplicateGroup("name", (first, second), (size, size))
        size_group = DuplicateGroup("size", (first, second, third), (size, size, size))
        actions = self.engine.preview_duplicate_cleanup([name_group, size_group], self.root, CleanupOptions(kinds=("name", "size"), keeper="first"))
        sources = [action.source for action in actions]
        self.assertEqual(len(sources), len(set(sources)))
        self.assertEqual(len(actions), 2)

    def test_cleanup_execute_and_undo_roundtrip(self):
        first = self.make_file("keep.bin", b"same-content")
        second = self.make_file("extra.bin", b"same-content")
        size = first.stat().st_size
        group = DuplicateGroup("hash", (first, second), (size, size))
        actions = self.engine.preview_duplicate_cleanup([group], self.root, CleanupOptions(kinds=("hash",), keeper="first"))
        self.assertEqual(len(actions), 1)
        done, log_path = self.engine.execute(actions, self.root / "logs")
        self.assertEqual(done[0].status, "成功")
        self.assertTrue(actions[0].destination.exists())
        undone = self.engine.undo(log_path)
        self.assertEqual(undone[0].status, "已撤销")
        self.assertTrue(first.exists())
        self.assertTrue(second.exists())

    def test_duplicate_groups_cache_mtimes(self):
        first = self.make_file("cached1.bin", b"same")
        second = self.make_file("cached2.bin", b"same")
        os.utime(first, (1000, 1000))
        os.utime(second, (2000, 2000))
        result = self.engine.find_duplicates(
            [first, second],
            DuplicateOptions(name_enabled=False, size_enabled=False, hash_enabled=True),
        )
        self.assertEqual(len(result.groups), 1)
        cached = result.groups[0].mtime_of
        self.assertAlmostEqual(cached[first], 1000, delta=2)
        self.assertAlmostEqual(cached[second], 2000, delta=2)

    def test_keeper_switch_uses_cached_mtimes_without_stat(self):
        first = self.make_file("old.bin", b"same")
        second = self.make_file("new.bin", b"same")
        group = DuplicateGroup(
            "hash",
            (first, second),
            (first.stat().st_size, second.stat().st_size),
            {first: 1000.0, second: 2000.0},
        )
        with mock.patch.object(Path, "stat", side_effect=AssertionError("不应再次 stat")):
            oldest = order_group_members(group.members, "oldest", group.mtime_of)
            newest = order_group_members(group.members, "newest", group.mtime_of)
        self.assertEqual(oldest[0], first)
        self.assertEqual(newest[0], second)

    def test_parallel_hash_matches_single_thread(self):
        files = []
        for index in range(4):
            files.append(self.make_file(f"same_{index}.bin", b"same-content" * 100))
        for index in range(2):
            files.append(self.make_file(f"other_{index}.bin", b"other-content" * 100))
        different = self.make_file("different.bin", b"different" * 100)
        options = DuplicateOptions(name_enabled=False, size_enabled=False, hash_enabled=True)
        single = self.engine.find_duplicates(
            files + [different],
            DuplicateOptions(**{**options.__dict__, "workers": 1}),
        )
        parallel = self.engine.find_duplicates(
            files + [different],
            DuplicateOptions(**{**options.__dict__, "workers": 4}),
        )
        self.assertEqual(
            {frozenset(group.members) for group in single.groups},
            {frozenset(group.members) for group in parallel.groups},
        )

    def test_name_groups_optimized_matches_reference(self):
        # 10,000 个文件名基准（每 5 个同 stem 副本，阈值 0.9，Windows / Python 3.14）：
        # 优化后约 8.5s，优化前全量两两比较约 235.5s，结果完全一致（约 27.8x）。
        names = [
            "alpha.mp4",
            "alpha - 副本.mp4",
            "alphb.mp4",
            "movie_01.mkv",
            "movie_02.mkv",
            "movie_01 (1).mkv",
            "photocopy.jpg",
            "photo.jpg",
            "completely-different.txt",
            "completely-different (1).txt",
        ]
        paths = [self.make_file(f"sub{index}/{name}") for index, name in enumerate(names)]
        threshold = 0.65
        actual = {frozenset(group) for group in find_name_groups(paths, threshold)}

        # 参考实现：与优化前一致的全量两两比较。
        dsu = DSU(paths)
        for i, first in enumerate(paths):
            for second in paths[i + 1:]:
                if SequenceMatcher(None, normalize_stem(first), normalize_stem(second)).ratio() >= threshold:
                    dsu.union(first, second)
        expected = {frozenset(group) for group in dsu.groups()}
        self.assertEqual(actual, expected)

    def test_cli_rejects_invalid_numeric_options(self):
        cases = [
            (["--name-thresh", "0"], "相似度阈值"),
            (["--name-thresh", "1.5"], "相似度阈值"),
            (["--size-percent", "-1"], "不能为负数"),
        ]
        for extra, message in cases:
            with self.subTest(extra=extra):
                stderr = io.StringIO()
                with contextlib.redirect_stderr(stderr), self.assertRaises(SystemExit) as raised:
                    cli.main([str(self.root), *extra])
                self.assertEqual(raised.exception.code, 2)
                self.assertIn(message, stderr.getvalue())

    def test_cli_reports_duplicates_and_writes_json(self):
        self.make_file("video1.mp4", b"z" * 2048)
        self.make_file("video1 - 副本.mp4", b"z" * 2048)
        json_path = self.root / "result.json"
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = cli.main([str(self.root), "--min-size", "0", "--hash", "--json", str(json_path)])
        self.assertEqual(code, 0)
        payload = json.loads(json_path.read_text(encoding="utf-8"))
        self.assertEqual(payload["file_count"], 2)
        self.assertEqual(len(payload["hash_groups"]), 1)
        self.assertEqual(len(payload["hash_groups"][0]), 2)
        self.assertIn("字节完全相同", output.getvalue())


if __name__ == "__main__":
    unittest.main()
