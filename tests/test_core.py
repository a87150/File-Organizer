import json
import os
import tempfile
import unittest
from datetime import date, datetime
from pathlib import Path

from file_organizer.core import (
    STATUS_UNDONE,
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

    def test_scan_and_hidden_filter(self):
        self.make_file("a.txt")
        self.make_file(".secret")
        self.make_file("nested/b.jpg")
        self.assertEqual([p.name for p in self.engine.scan(self.root)], ["a.txt"])
        self.assertEqual(len(self.engine.scan(self.root, recursive=True)), 2)
        self.assertEqual(len(self.engine.scan(self.root, recursive=True, include_hidden=True)), 3)

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
        self.assertEqual(done[0].status, "成功")
        self.assertTrue(actions[0].destination.exists())
        self.assertIsNotNone(log_path)
        undone = self.engine.undo(log_path)
        self.assertEqual(undone[0].status, "已撤销")
        self.assertTrue(image.exists())

    def test_name_rules_and_unique_destination(self):
        source = self.make_file("合同-甲方.txt")
        target = self.make_file("合同/合同-甲方.txt")
        actions = self.engine.preview_organize([source], self.root, OrganizeOptions(mode="name", name_rules=(("合同", "合同"),)))
        self.assertNotEqual(actions[0].destination, target)
        self.assertEqual(actions[0].destination.name, "合同-甲方 (1).txt")

    def test_sanitize_invalid_windows_filename(self):
        self.assertEqual(sanitize_component('a:b?c*'), "a_b_c_")

    def test_search_then_rename_only_matches(self):
        report = self.make_file("年度报告.PDF", b"x" * 20)
        self.make_file("临时报告.txt", b"x" * 20)
        self.make_file("年度图片.jpg", b"x" * 20)
        matches = self.engine.filter_files(
            self.engine.scan(self.root),
            SearchOptions(name_pattern="年度", extensions=(" pdf ",), min_size_mb=0),
        )
        self.assertEqual(matches, [report])
        actions = self.engine.preview_rename(matches, RenameOptions(prefix="归档_"))
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
            self.engine.scan(self.root),
            SearchOptions(extensions=(".pdf",), modified_from=date(2026, 8, 1), modified_to=date(2026, 8, 31)),
        )
        self.assertEqual(matches, [new_pdf])

    def test_search_files_without_extension(self):
        plain = self.make_file("LICENSE")
        self.make_file("readme.md")
        matches = self.engine.filter_files(self.engine.scan(self.root), SearchOptions(extensions=("",)))
        self.assertEqual(matches, [plain])

    def test_search_multiple_extensions(self):
        pdf = self.make_file("document.pdf")
        text = self.make_file("notes.txt")
        self.make_file("image.png")
        matches = self.engine.filter_files(self.engine.scan(self.root), SearchOptions(extensions=(".pdf", ".txt")))
        self.assertEqual(matches, [pdf, text])

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
        files = self.engine.scan(self.root)
        vanished.unlink()
        matches = self.engine.filter_files(files, SearchOptions(min_size_mb=0))
        self.assertEqual(matches, [first])

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
