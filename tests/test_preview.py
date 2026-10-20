import tempfile
import unittest
from pathlib import Path
from unittest import mock

from file_organizer import preferences
from file_organizer.preview import (
    COLUMN_KEYS,
    DEFAULT_VISIBLE,
    PreviewRow,
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


if __name__ == "__main__":
    unittest.main()
