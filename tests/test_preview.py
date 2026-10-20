import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from file_organizer import preferences
from file_organizer.core import Action, ActionStatus
from file_organizer.preview import (
    COLUMN_KEYS,
    DEFAULT_VISIBLE,
    PreviewRow,
    build_action_row,
    file_type_label,
    format_modified,
    natural_key,
    sort_preview_rows,
)


class PreviewHelpersTests(unittest.TestCase):
    def test_file_type_label(self) -> None:
        self.assertEqual(file_type_label(Path("photo.JPG")), "图片 · .jpg")
        self.assertEqual(file_type_label(Path("movie.mkv")), "视频 · .mkv")
        self.assertEqual(file_type_label(Path("archive.xyz")), "其他 · .xyz")
        self.assertEqual(file_type_label(Path("README")), "无扩展名")

    def test_format_modified(self) -> None:
        self.assertEqual(format_modified(None), "—")
        self.assertRegex(format_modified(0), r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$")

    def test_natural_key_orders_numbers(self) -> None:
        names = ["file10.txt", "file2.txt", "file1.txt"]
        self.assertEqual(sorted(names, key=natural_key), ["file1.txt", "file2.txt", "file10.txt"])

    def test_sort_flat_rows(self) -> None:
        rows = [
            PreviewRow(source="b.txt", size_value=20, modified_ts=2.0),
            PreviewRow(source="a.txt", size_value=30, modified_ts=3.0),
            PreviewRow(source="c.txt", size_value=10, modified_ts=1.0),
        ]
        by_name = sort_preview_rows(rows, "source")
        self.assertEqual([row.source for row in by_name], ["a.txt", "b.txt", "c.txt"])
        by_size = sort_preview_rows(rows, "size", descending=True)
        self.assertEqual([row.source for row in by_size], ["a.txt", "b.txt", "c.txt"])
        by_time = sort_preview_rows(rows, "modified")
        self.assertEqual([row.modified_ts for row in by_time], [1.0, 2.0, 3.0])

    def test_status_sort_uses_semantic_order(self) -> None:
        rows = [PreviewRow(status="失败"), PreviewRow(status="保留"), PreviewRow(status="成功")]
        ordered = sort_preview_rows(rows, "status")
        self.assertEqual([row.status for row in ordered], ["保留", "成功", "失败"])

    def test_group_sort_keeps_headers_with_members(self) -> None:
        rows = [
            PreviewRow(status="分组", source="组一", group=1, is_header=True),
            PreviewRow(status="候选", source="big.txt", size_value=30, group=1),
            PreviewRow(status="保留", source="small.txt", size_value=10, group=1),
            PreviewRow(status="分组", source="组二", group=2, is_header=True),
            PreviewRow(status="候选", source="other.txt", size_value=50, group=2),
        ]
        ordered = sort_preview_rows(rows, "size")
        self.assertEqual(
            [(row.source, row.is_header) for row in ordered],
            [("组一", True), ("small.txt", False), ("big.txt", False), ("组二", True), ("other.txt", False)],
        )

    def test_all_column_keys_have_titles(self) -> None:
        self.assertEqual(len(COLUMN_KEYS), len(set(COLUMN_KEYS)))
        self.assertIn("modified", COLUMN_KEYS)
        self.assertIn("file_type", COLUMN_KEYS)


class ActionRowTests(unittest.TestCase):
    def test_action_row_uses_destination_stat_once(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            source = root / "source.txt"
            destination = root / "renamed.txt"
            source.write_bytes(b"src")
            destination.write_bytes(b"destination")
            os.utime(source, (1000, 1000))
            os.utime(destination, (2000, 2000))
            action = Action("rename", source, destination)

            def relative(path: Path) -> str:
                return path.name

            def folder_text(path: Path) -> str:
                return path.parent.name

            original_stat = Path.stat
            calls: list[Path] = []

            def counting_stat(path: Path):
                calls.append(path)
                return original_stat(path)

            with mock.patch.object(Path, "stat", counting_stat):
                row = build_action_row(action, root, relative, folder_text)
            self.assertEqual(len(calls), 1)
            self.assertEqual(row.size_value, len(b"destination"))
            self.assertEqual(row.size_text, "11 B")
            self.assertAlmostEqual(row.modified_ts, 2000, delta=2)
            self.assertEqual(row.destination, "renamed.txt")
            self.assertEqual(row.status, "待执行")
            self.assertEqual(row.tags, ("pending",))

    def test_action_row_falls_back_to_source_when_destination_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            source = root / "source.txt"
            source.write_bytes(b"abc")
            action = Action("move", source, root / "not-created" / "source.txt")
            row = build_action_row(action, root, lambda path: path.name, lambda path: path.parent.name)
            self.assertEqual(row.size_value, 3)
            self.assertIn("not-created", row.destination)

    def test_failed_action_row_tag(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            source = root / "source.txt"
            source.write_bytes(b"abc")
            action = Action("rename", source, root / "target.txt", ActionStatus.FAILED, "目标已存在")
            row = build_action_row(action, root, lambda path: path.name, lambda path: path.parent.name)
            self.assertEqual(row.status, "失败")
            self.assertEqual(row.tags, ("failed",))


class PreviewPreferencesTests(unittest.TestCase):
    def test_visible_columns_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "settings.json"
            with mock.patch.object(preferences, "settings_path", return_value=path):
                preferences.save_visible_columns(["source", "size", "folder"])
                self.assertEqual(preferences.load_visible_columns(), {"source", "size", "folder"})
                # 「原文件」固定显示
                preferences.save_visible_columns(["size"])
                self.assertEqual(preferences.load_visible_columns(), {"source", "size"})
                # 损坏的配置文件回退到默认字段
                path.write_text("not json", encoding="utf-8")
                self.assertEqual(preferences.load_visible_columns(), set(DEFAULT_VISIBLE))

    def test_preview_sort_roundtrip_and_invalid_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "settings.json"
            with mock.patch.object(preferences, "settings_path", return_value=path):
                self.assertEqual(preferences.load_preview_sort(), (None, False))
                preferences.save_preview_sort("size", True)
                self.assertEqual(preferences.load_preview_sort(), ("size", True))
                preferences.save_preview_sort("not-a-column", True)
                self.assertEqual(preferences.load_preview_sort(), (None, False))
                preferences.save_preview_sort(None)
                self.assertEqual(preferences.load_preview_sort(), (None, False))

    def test_atomic_save_keeps_old_file_when_replace_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "settings.json"
            with mock.patch.object(preferences, "settings_path", return_value=path):
                preferences.save_visible_columns(["source", "size"])
                with mock.patch.object(preferences.os, "replace", side_effect=OSError("disk full")):
                    preferences.save_visible_columns(["source", "folder"])
                self.assertEqual(preferences.load_visible_columns(), {"source", "size"})
                temp = path.with_name(path.name + ".tmp")
                self.assertFalse(temp.exists())

    def test_columns_and_sort_are_saved_together(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "settings.json"
            with mock.patch.object(preferences, "settings_path", return_value=path):
                preferences.save_visible_columns(["source", "modified"])
                preferences.save_preview_sort("modified", True)
                self.assertEqual(preferences.load_visible_columns(), {"source", "modified"})
                self.assertEqual(preferences.load_preview_sort(), ("modified", True))


if __name__ == "__main__":
    unittest.main()
