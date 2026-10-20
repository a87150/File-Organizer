import tempfile
import unittest
from pathlib import Path

from file_organizer import app, theme
from file_organizer.regex_help import RegexHelpWindow
from file_organizer.theme import apply_window_frame, _colorref
from file_organizer.widgets import SeamlessComboBox, bind_combo_toggle


class ThemeImportTests(unittest.TestCase):
    def test_title_bar_theme_constants(self) -> None:
        self.assertTrue(theme.TEXT_PRIMARY.startswith("#"))
        self.assertTrue(theme.BORDER.startswith("#"))
        self.assertIs(app.apply_window_frame, theme.apply_window_frame)

    def test_colorref_is_windows_bgr_order(self) -> None:
        self.assertEqual(_colorref("#0071E3"), 0xE37100)
        self.assertEqual(_colorref("#FFFFFF"), 0xFFFFFF)

    def test_apply_window_frame_ignores_broken_window(self) -> None:
        class FakeWindow:
            def winfo_id(self):
                raise AttributeError("window destroyed")

        apply_window_frame(FakeWindow())


class PrivateApiGuardTests(unittest.TestCase):
    def test_restore_right_side_ignores_missing_canvas(self) -> None:
        class MissingCanvas:
            @property
            def _canvas(self):
                raise AttributeError("_canvas")

        # 依赖 CTk 内部结构；缺失时应静默降级而不是让下拉框报错。
        SeamlessComboBox._restore_right_side(MissingCanvas())

    def test_combo_toggle_ignores_missing_dropdown(self) -> None:
        class FakeCombo:
            def bind(self, sequence, callback):
                self.sequence = sequence
                self.callback = callback

            @property
            def _dropdown_menu(self):
                raise AttributeError("_dropdown_menu")

        widget = FakeCombo()
        bind_combo_toggle(widget)
        self.assertEqual(widget.sequence, "<Button-1>")
        widget.callback()

    def test_regex_help_page_switch_ignores_missing_parent_canvas(self) -> None:
        class FakeFrame:
            def __init__(self):
                self.hidden = False

            def pack_forget(self):
                self.hidden = True

            def pack(self, **kwargs):
                self.hidden = False

        class FakeSelector:
            def __init__(self):
                self.selected = -1

            def select(self, index):
                self.selected = index

        class FakeBody:
            @property
            def _parent_canvas(self):
                raise AttributeError("_parent_canvas")

        class FakeHelp:
            def __init__(self):
                self._pages = [FakeFrame(), FakeFrame()]
                self.selector = FakeSelector()
                self.body = FakeBody()

        fake = FakeHelp()
        RegexHelpWindow._show_page(fake, 1)
        self.assertTrue(fake._pages[0].hidden)
        self.assertFalse(fake._pages[1].hidden)
        self.assertEqual(fake.selector.selected, 1)


class FolderTextTests(unittest.TestCase):
    def test_root_folder_has_readable_label(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            nested = root / "sub" / "file.txt"
            fake = object.__new__(app.FileOrganizerApp)
            fake.scan_root = root
            self.assertEqual(app.FileOrganizerApp._folder_text(fake, root / "file.txt"), "（根目录）")
            self.assertEqual(app.FileOrganizerApp._folder_text(fake, nested), "sub")


class CopyFeedbackTests(unittest.TestCase):
    def test_copy_button_restores_after_delay(self) -> None:
        class FakeButton:
            def __init__(self):
                self.text = "复制"
                self.exists = True

            def configure(self, **kwargs):
                self.text = kwargs.get("text", self.text)

            def winfo_exists(self):
                return self.exists

        class FakeHelp:
            def __init__(self):
                self.copied = None
                self.callbacks = []

            def clipboard_clear(self):
                self.copied = ""

            def clipboard_append(self, value):
                self.copied = value

            def after(self, delay, callback):
                self.callbacks.append((delay, callback))

        button = FakeButton()
        fake = FakeHelp()
        RegexHelpWindow._copy(fake, r"\d+", button)
        self.assertEqual(fake.copied, r"\d+")
        self.assertEqual(button.text, "已复制 ✓")
        self.assertEqual(fake.callbacks[0][0], 800)
        fake.callbacks[0][1]()
        self.assertEqual(button.text, "复制")


if __name__ == "__main__":
    unittest.main()
