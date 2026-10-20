import unittest

from file_organizer.utils import format_size, normalize_extension, resource_path


class UtilsTests(unittest.TestCase):
    def test_format_size_uses_integer_bytes(self) -> None:
        self.assertEqual(format_size(0), "0 B")
        self.assertEqual(format_size(512), "512 B")
        self.assertEqual(format_size(1023), "1023 B")
        self.assertEqual(format_size(1024), "1.0 KB")
        self.assertEqual(format_size(1536), "1.5 KB")

    def test_normalize_extension(self) -> None:
        self.assertEqual(normalize_extension(" PDF "), ".pdf")
        self.assertEqual(normalize_extension(".JPG"), ".jpg")
        self.assertEqual(normalize_extension(""), "")
        self.assertEqual(normalize_extension("   "), "")

    def test_resource_path_returns_absolute_source_path(self) -> None:
        path = resource_path("file_organizer/assets/app.ico")
        self.assertTrue(path.is_absolute())
        self.assertEqual(path.name, "app.ico")


if __name__ == "__main__":
    unittest.main()
