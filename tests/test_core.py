import ctypes
import json
import os
import sys
import tempfile
import unittest
from datetime import date, datetime
from pathlib import Path

from file_organizer.core import (
    STATUS_UNDONE,
    Action,
    ActionStatus,
    FileEntry,
    OrganizerEngine,
    OrganizeOptions,
    RenameOptions,
    SearchOptions,
    sanitize_component,
)


class OrganizerEngineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        # resolve：避免 TEMP 为 8.3 短路径时与扫描结果的长路径不一致
        self.root = Path(self.temp.name).resolve()
        self.engine = OrganizerEngine()

    def tearDown(self):
        self.temp.cleanup()

    def make_file(self, name: str, content: bytes = b"x") -> Path:
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return path

    def scan_entries(self, **kwargs) -> list[FileEntry]:
        return self.engine.scan(self.root, **kwargs)

    def scan_paths(self, **kwargs) -> list[Path]:
        return [entry.path for entry in self.scan_entries(**kwargs)]

    def test_scan_and_hidden_filter(self):
        self.make_file("a.txt")
        self.make_file(".secret")
        self.make_file("nested/b.jpg")
        self.assertEqual([p.name for p in self.scan_paths()], ["a.txt"])
        self.assertEqual(len(self.scan_paths(recursive=True)), 2)
        self.assertEqual(len(self.scan_paths(recursive=True, include_hidden=True)), 3)

    def test_scan_returns_cached_size_and_mtime(self):
        path = self.make_file("sized.txt", b"abc")
        stamp = 1_700_000_000
        os.utime(path, (stamp, stamp))
        entry = self.scan_entries()[0]
        self.assertEqual(entry.path, path)
        self.assertEqual(entry.size, 3)
        self.assertAlmostEqual(entry.mtime or 0, stamp, delta=2)

    def test_scan_skips_log_directory_even_when_hidden_included(self):
        self.make_file("keep.txt")
        log_file = self.make_file(".file_organizer_logs/operation_1.jsonl", b"{}")
        for include_hidden in (False, True):
            paths = self.scan_paths(recursive=True, include_hidden=include_hidden)
            self.assertIn(self.root / "keep.txt", paths)
            self.assertNotIn(log_file, paths)

    @unittest.skipUnless(sys.platform == "win32", "仅 Windows 有 FILE_ATTRIBUTE_HIDDEN")
    def test_scan_skips_windows_hidden_attribute(self):
        visible = self.make_file("visible.txt")
        hidden = self.make_file("hidden.txt")
        kernel32 = ctypes.windll.kernel32
        self.assertTrue(kernel32.SetFileAttributesW(str(hidden), 0x2))
        self.addCleanup(kernel32.SetFileAttributesW, str(hidden), 0x80)

        self.assertEqual([entry.path for entry in self.scan_entries()], [visible])
        self.assertEqual(
            {entry.path for entry in self.scan_entries(include_hidden=True)},
            {visible, hidden},
        )

    def test_rename_preview_preserves_extension(self):
        source = self.make_file("report FINAL.pdf")
        actions = self.engine.preview_rename([source], RenameOptions(prefix="2026_", find=" FINAL", replace="", case="lower", add_counter=True, counter_start=7, counter_width=2))
        self.assertEqual(actions[0].destination.name, "2026_report_07.pdf")

    def test_rename_can_change_extension(self):
        source = self.make_file("report.txt")
        actions = self.engine.preview_rename([source], RenameOptions(new_extension=".md"))
        self.assertEqual(actions[0].destination.name, "report.md")

    def test_organize_by_type_and_execute_undo(self):
        image = self.make_file("photo.JPG")
        actions = self.engine.preview_organize([image], self.root, OrganizeOptions(mode="type"))
        self.assertEqual(actions[0].destination.parent.name, "图片")
        done, log_path = self.engine.execute(actions, self.root / "logs")
        self.assertEqual(done[0].status, ActionStatus.SUCCESS)
        self.assertTrue(actions[0].destination.exists())
        self.assertIsNotNone(log_path)
        undone = self.engine.undo(log_path)
        self.assertEqual(undone[0].status, STATUS_UNDONE)
        self.assertTrue(image.exists())

    def test_name_rules_and_unique_destination(self):
        source = self.make_file("合同-甲方.txt")
        target = self.make_file("合同/合同-甲方.txt")
        actions = self.engine.preview_organize([source], self.root, OrganizeOptions(mode="name", name_rules=(("合同", "合同"),)))
        self.assertNotEqual(actions[0].destination, target)
        self.assertEqual(actions[0].destination.name, "合同-甲方 (1).txt")

    def test_organize_case_insensitive_collision_reserved(self):
        first = self.make_file("AAA.pdf", b"1")
        second = self.make_file("sub/aaa.pdf", b"2")
        actions = self.engine.preview_organize([first, second], self.root, OrganizeOptions(mode="type"))
        destinations = [str(action.destination).casefold() for action in actions]
        self.assertEqual(len(destinations), 2)
        self.assertEqual(len(set(destinations)), 2)

    def test_sanitize_invalid_windows_filename(self):
        self.assertEqual(sanitize_component('a:b?c*'), "a_b_c_")

    def test_sanitize_truncates_long_component(self):
        cleaned = sanitize_component("x" * 400)
        self.assertEqual(len(cleaned), 255)

    def test_search_then_rename_only_matches(self):
        report = self.make_file("年度报告.PDF", b"x" * 20)
        self.make_file("临时报告.txt", b"x" * 20)
        self.make_file("年度图片.jpg", b"x" * 20)
        matches = self.engine.filter_files(
            self.scan_entries(),
            SearchOptions(name_pattern="年度", extensions=(" pdf ",), min_size_mb=0),
        )
        self.assertEqual([entry.path for entry in matches], [report])
        actions = self.engine.preview_rename([entry.path for entry in matches], RenameOptions(prefix="归档_"))
        self.assertEqual(actions[0].destination.name, "归档_年度报告.PDF")

    def test_search_by_detected_extension_and_modified_date(self):
        old_pdf = self.make_file("old.pdf")
        new_pdf = self.make_file("new.pdf")
        self.make_file("new.txt")
        old_stamp = datetime(2025, 1, 15, 12, 0).timestamp()
        new_stamp = datetime(2026, 8, 20, 12, 0).timestamp()
        os.utime(old_pdf, (old_stamp, old_stamp))
        os.utime(new_pdf, (new_stamp, new_stamp))
        matches = self.engine.filter_files(
            self.scan_entries(),
            SearchOptions(extensions=(".pdf",), modified_from=date(2026, 8, 1), modified_to=date(2026, 8, 31)),
        )
        self.assertEqual([entry.path for entry in matches], [new_pdf])

    def test_search_files_without_extension(self):
        plain = self.make_file("LICENSE")
        self.make_file("readme.md")
        matches = self.engine.filter_files(self.scan_entries(), SearchOptions(extensions=("",)))
        self.assertEqual([entry.path for entry in matches], [plain])

    def test_search_multiple_extensions(self):
        pdf = self.make_file("document.pdf")
        text = self.make_file("notes.txt")
        self.make_file("image.png")
        matches = self.engine.filter_files(self.scan_entries(), SearchOptions(extensions=(".pdf", ".txt")))
        self.assertEqual([entry.path for entry in matches], [pdf, text])

    def test_extract_filename_part_as_category(self):
        first = self.make_file("项目A_合同_001.pdf")
        second = self.make_file("项目B_报价.xlsx")
        options = OrganizeOptions(mode="extract", extract_pattern=r"^([^_]+)_", extract_group="1")
        actions = self.engine.preview_organize([first, second], self.root, options)
        self.assertEqual([action.destination.parent.name for action in actions], ["项目A", "项目B"])

    def test_extract_named_group(self):
        source = self.make_file("客户-华东-清单.csv")
        options = OrganizeOptions(mode="extract", extract_pattern=r"客户-(?P<region>[^-]+)-", extract_group="region")
        actions = self.engine.preview_organize([source], self.root, options)
        self.assertEqual(actions[0].destination.parent.name, "华东")

    def test_filter_files_skips_vanished_files(self):
        first = self.make_file("keep.txt")
        vanished = self.make_file("gone.txt")
        files = self.scan_entries()
        vanished.unlink()
        matches = self.engine.filter_files(files, SearchOptions(min_size_mb=0))
        self.assertEqual([entry.path for entry in matches], [first])

    def test_execute_refuses_to_overwrite_existing_destination(self):
        blocked_source = self.make_file("blocked.txt", b"new")
        target = self.make_file("target.txt", b"original")
        moving_source = self.make_file("move.txt", b"move me")
        actions = [
            Action("move", blocked_source, target),
            Action("move", moving_source, self.root / "moved.txt"),
        ]
        done, log_path = self.engine.execute(actions, self.root / "logs")
        self.assertEqual([item.status for item in done], [ActionStatus.FAILED, ActionStatus.SUCCESS])
        self.assertIn("已存在", done[0].message)
        self.assertEqual(target.read_bytes(), b"original")
        self.assertTrue(blocked_source.exists())
        self.assertTrue((self.root / "moved.txt").exists())
        self.assertIsNotNone(log_path)
        lines = [line for line in log_path.read_text(encoding="utf-8").splitlines() if line.strip()]
        self.assertEqual(len(lines), 1)
        self.assertEqual(json.loads(lines[0])["status"], "成功")

    def test_execute_writes_jsonl_log_incrementally(self):
        first = self.make_file("a.txt")
        second = self.make_file("b.txt")
        actions = self.engine.preview_rename([first, second], RenameOptions(prefix="new_"))
        done, log_path = self.engine.execute(actions, self.root / "logs")
        self.assertEqual(len(done), 2)
        self.assertEqual(log_path.suffix, ".jsonl")
        lines = [line for line in log_path.read_text(encoding="utf-8").splitlines() if line.strip()]
        self.assertEqual(len(lines), 2)
        self.assertEqual(json.loads(lines[0])["operation"], "rename")
        undone = self.engine.undo(log_path)
        self.assertEqual([item.status for item in undone], [STATUS_UNDONE, STATUS_UNDONE])

    def test_undo_supports_legacy_json_array_log(self):
        # 旧版本日志是 JSON 数组，撤销应保持兼容
        source = self.make_file("legacy.txt")
        destination = self.root / "legacy_moved.txt"
        source.rename(destination)
        legacy_log = self.root / "logs" / "operation_legacy.json"
        legacy_log.parent.mkdir(parents=True, exist_ok=True)
        legacy_log.write_text(json.dumps([{"operation": "move", "source": str(source), "destination": str(destination)}]), encoding="utf-8")
        results = self.engine.undo(legacy_log)
        self.assertEqual(results[0].status, STATUS_UNDONE)
        self.assertTrue(source.exists())

    def test_undo_rejects_paths_outside_log_workspace(self):
        outside_temp = tempfile.TemporaryDirectory()
        self.addCleanup(outside_temp.cleanup)
        outside = Path(outside_temp.name).resolve() / "outside.txt"
        outside.write_bytes(b"outside")
        current = self.make_file("inside.txt", b"inside")
        log = self.root / "logs" / "operation_external.jsonl"
        log.parent.mkdir(parents=True, exist_ok=True)
        log.write_text(
            json.dumps({"operation": "move", "source": str(outside), "destination": str(current)}) + "\n",
            encoding="utf-8",
        )
        results = self.engine.undo(log)
        self.assertEqual(results[0].status, ActionStatus.FAILED)
        self.assertIn("工作目录", results[0].message)
        self.assertTrue(current.exists())
        self.assertTrue(outside.exists())
        self.assertEqual(outside.read_bytes(), b"outside")

    def test_undo_rejects_invalid_log_with_friendly_error(self):
        empty_log = self.root / "logs" / "operation_empty.jsonl"
        empty_log.parent.mkdir(parents=True, exist_ok=True)
        empty_log.write_text("", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "无法读取日志"):
            self.engine.undo(empty_log)
        broken_log = self.root / "logs" / "operation_broken.jsonl"
        broken_log.write_text("{not json}", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "无法读取日志"):
            self.engine.undo(broken_log)
        missing_fields = self.root / "logs" / "operation_missing.jsonl"
        missing_fields.write_text(json.dumps({"operation": "move"}) + "\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "无法读取日志"):
            self.engine.undo(missing_fields)


if __name__ == "__main__":
    unittest.main()
