from __future__ import annotations

import queue
import sys
import threading
import tkinter as tk
from collections import Counter
from datetime import date, datetime, timedelta
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import customtkinter as ctk

from .core import (
    STATUS_FAILED,
    STATUS_SUCCESS,
    STATUS_UNDONE,
    Action,
    OrganizerEngine,
)
from .duplicates import OperationCancelled
from .preferences import load_visible_columns, save_visible_columns
from .preview import (
    COLUMN_ANCHORS,
    COLUMN_KEYS,
    COLUMN_TITLES,
    COLUMN_WIDTHS,
    DEFAULT_VISIBLE,
    FIXED_COLUMNS,
    PreviewRow,
    file_type_label,
    format_modified,
    sort_preview_rows,
)
from .regex_help import RegexHelpWindow
from .tabs import DuplicatesTabMixin, HistoryTabMixin, OrganizeTabMixin, RenameTabMixin
from .theme import (
    ACCENT,
    APP_BG,
    CARD_BG,
    FONT_FAMILY,
    SCROLL_THUMB,
    SCROLL_THUMB_ACTIVE,
    SEGMENT_BG,
    TEXT_SECONDARY,
    configure_styles,
)
from .utils import format_size
from .widgets import (  # noqa: F401  (部分供各页签构建时使用)
    FIELD_HEIGHT,
    RoundedButton,
    RoundedPanel,
    TabHost,
    checkbox,
    entry,
    label,
    scrollbar,
)

TREE_CHUNK_SIZE = 500
MAX_PREVIEW_ROWS = 20000


class FileOrganizerApp(RenameTabMixin, OrganizeTabMixin, DuplicatesTabMixin, HistoryTabMixin, ctk.CTk):
    def __init__(self) -> None:
        super().__init__(fg_color=APP_BG)
        self.title("文件夹整理工具")
        self.geometry("1180x760")
        self.minsize(900, 600)
        self.engine = OrganizerEngine()
        self.files: list[Path] = []
        self.matched_files: list[Path] | None = None
        self.actions: list[Action] = []
        self.last_log: Path | None = None
        self.scan_root: Path | None = None
        self.events: queue.Queue[tuple[str, object]] = queue.Queue()
        self.busy = False
        self.cancel_event: threading.Event | None = None
        self._tree_generation = 0
        self._preview_rows: list[PreviewRow] = []
        self._sort_column: str | None = None
        self._sort_desc = False
        self._visible_columns = load_visible_columns()
        self._column_popup: ctk.CTkToplevel | None = None
        self._column_vars: dict[str, tk.BooleanVar] = {}

        self.folder_var = tk.StringVar(value=str(Path.home() / "Downloads"))
        self.recursive_var = tk.BooleanVar(value=False)
        self.hidden_var = tk.BooleanVar(value=False)
        self.status_var = tk.StringVar(value="请选择文件夹后扫描")
        self._build_ui()
        self.update_idletasks()
        self._apply_window_frame()
        self.after(100, self._poll_events)

    def _build_ui(self) -> None:
        configure_styles(self)
        root = ctk.CTkFrame(self, corner_radius=0, fg_color=APP_BG)
        root.pack(fill="both", expand=True, padx=18, pady=18)

        intro = ctk.CTkFrame(root, corner_radius=0, fg_color="transparent")
        intro.pack(fill="x", pady=(0, 12))
        label(intro, "先筛选和预览，再安全地批量重命名、分类或清理重复文件。", color=TEXT_SECONDARY).pack(side="left")
        RoundedButton(intro, text="正则帮助", variant="secondary", padx=14, pady=6, height=FIELD_HEIGHT, command=self._show_regex_help).pack(side="right")

        chooser_panel = RoundedPanel(root, padding=(14, 12))
        chooser_panel.pack(fill="x")
        chooser = chooser_panel.inner
        label(chooser, "工作目录").pack(side="left", padx=(0, 10))
        entry(chooser, textvariable=self.folder_var).pack(side="left", fill="x", expand=True)
        RoundedButton(chooser, text="浏览…", variant="secondary", padx=14, pady=7, height=FIELD_HEIGHT, command=self._choose_folder).pack(side="left", padx=(8, 0))
        checkbox(chooser, "包含子文件夹", self.recursive_var).pack(side="left", padx=10)
        checkbox(chooser, "包含隐藏文件", self.hidden_var).pack(side="left")
        self.scan_button = RoundedButton(chooser, text="扫描文件", variant="primary", padx=18, pady=7, height=FIELD_HEIGHT, command=self._scan)
        self.scan_button.pack(side="left", padx=(10, 0))

        body = ttk.Panedwindow(root, orient="horizontal")
        body.pack(fill="both", expand=True, pady=12)

        left_wrap = ctk.CTkFrame(body, corner_radius=0, fg_color=APP_BG)
        body.add(left_wrap, weight=2)
        left_panel = RoundedPanel(left_wrap, padding=(10, 10), fill=APP_BG, border=None)
        left_panel.pack(fill="both", expand=True, padx=(0, 3))

        self.tab_host = TabHost(left_panel.inner, surface=APP_BG, width=380)
        self.tab_host.pack(fill="both", expand=True)
        self._build_rename_tab(self.tab_host)
        self._build_organize_tab(self.tab_host)
        self._build_duplicates_tab(self.tab_host)
        self._build_history_tab(self.tab_host)

        preview_wrap = ctk.CTkFrame(body, corner_radius=0, fg_color=APP_BG)
        body.add(preview_wrap, weight=3)
        preview_panel = RoundedPanel(preview_wrap, padding=(14, 12))
        preview_panel.pack(fill="both", expand=True, padx=(3, 0))
        preview = preview_panel.inner
        header = ctk.CTkFrame(preview, corner_radius=0, fg_color="transparent")
        header.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 8))
        label(header, "文件与操作预览", size=13, weight="bold").pack(side="left")
        label(header, "点击列名排序", size=11, color=TEXT_SECONDARY).pack(side="left", padx=(10, 0))
        self.column_button = RoundedButton(
            header,
            text="显示字段",
            variant="secondary",
            padx=12,
            pady=5,
            height=30,
            command=self._toggle_column_picker,
        )
        self.column_button.pack(side="right")

        self.tree = ttk.Treeview(preview, columns=COLUMN_KEYS, show="headings", selectmode="extended")
        self.tree.tag_configure("match", foreground="#0071E3")
        self.tree.tag_configure("success", foreground="#248A3D")
        self.tree.tag_configure("failed", foreground="#D70015")
        self.tree.tag_configure("pending", foreground="#6E6E73")
        self.tree.tag_configure("dup-hash", foreground="#248A3D", font=(FONT_FAMILY, 11, "bold"))
        self.tree.tag_configure("dup-size", foreground="#B25000", font=(FONT_FAMILY, 11, "bold"))
        self.tree.tag_configure("dup-name", foreground="#0071E3", font=(FONT_FAMILY, 11, "bold"))
        self.tree.tag_configure("keep", foreground="#248A3D")
        self.tree.tag_configure("candidate", foreground="#B25000")
        for col in COLUMN_KEYS:
            self.tree.heading(col, text=COLUMN_TITLES[col], command=lambda key=col: self._sort_preview(key))
            self.tree.column(col, width=COLUMN_WIDTHS[col], anchor=COLUMN_ANCHORS[col])
        self.tree.configure(displaycolumns=self._display_columns())
        ybar = scrollbar(preview, orientation="vertical", command=self.tree.yview)
        xbar = scrollbar(preview, orientation="horizontal", command=self.tree.xview, height=12)
        self.tree.configure(yscrollcommand=ybar.set, xscrollcommand=xbar.set)
        self.tree.grid(row=1, column=0, sticky="nsew")
        ybar.grid(row=1, column=1, sticky="ns", padx=(6, 0))
        xbar.grid(row=2, column=0, sticky="ew", pady=(6, 0))
        preview.rowconfigure(1, weight=1)
        preview.columnconfigure(0, weight=1)

        bottom_panel = RoundedPanel(root, padding=(14, 12))
        bottom_panel.pack(fill="x")
        bottom = bottom_panel.inner
        label(bottom, "●", color=ACCENT).pack(side="left", padx=(0, 7))
        label(bottom, textvariable=self.status_var, color=TEXT_SECONDARY).pack(side="left")
        right_bar = ctk.CTkFrame(bottom, corner_radius=0, fg_color="transparent")
        right_bar.pack(side="right")
        self.progress = ctk.CTkProgressBar(right_bar, width=160, height=6, corner_radius=3, fg_color=SEGMENT_BG, progress_color=ACCENT, mode="indeterminate")
        self.execute_btn = RoundedButton(right_bar, text="执行预览操作", variant="primary", padx=20, pady=8, command=self._execute, state="disabled")
        self.execute_btn.pack(side="left")
        self.cancel_button = RoundedButton(right_bar, text="取消", variant="secondary", padx=16, pady=8, command=self._cancel_current)
        self._reset_progress()

    def _apply_window_frame(self) -> None:
        """让系统标题栏与窗口主体同色（Windows 11 支持；其他系统静默忽略）。"""
        if sys.platform != "win32":
            return
        try:
            import ctypes

            def colorref(hex_color: str) -> int:
                value = int(hex_color.lstrip("#"), 16)
                red, green, blue = (value >> 16) & 0xFF, (value >> 8) & 0xFF, value & 0xFF
                return (blue << 16) | (green << 8) | red

            hwnd = ctypes.windll.user32.GetParent(self.winfo_id())
            if not hwnd:
                return
            for attribute, color in ((35, APP_BG), (36, TEXT_PRIMARY), (34, BORDER)):
                data = ctypes.c_int(colorref(color))
                ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, attribute, ctypes.byref(data), ctypes.sizeof(data))
        except Exception:
            pass

    # ------------------------------------------------------------------ 选择目录

    def _show_regex_help(self) -> None:
        """右上角「正则」按钮：打开正则基础教学 / 常用模板。"""
        existing = getattr(self, "_regex_window", None)
        if existing is not None and existing.winfo_exists():
            existing.deiconify()
            existing.lift()
            existing.focus_force()
            return
        self._regex_window = RegexHelpWindow(self)

    def _choose_folder(self) -> None:
        selected = filedialog.askdirectory(initialdir=self.folder_var.get())
        if selected:
            self.folder_var.set(selected)
            self.files = []
            self.matched_files = None
            self.actions = []
            self.last_log = None
            self.scan_root = None
            self.dup_result = None
            self._clear_tree()

    # ------------------------------------------------------------------ 后台任务

    def _run_background(self, label: str, function, *, cancellable: bool = False) -> None:
        if self.busy:
            self.status_var.set("正在执行上一个任务，请稍候…")
            return
        self.busy = True
        self.cancel_event = threading.Event() if cancellable else None
        self.scan_button.configure(state="disabled")
        self.execute_btn.configure(state="disabled")
        if cancellable:
            self.cancel_button.configure(state="normal")
            self.cancel_button.pack(side="left", padx=(0, 10), before=self.execute_btn)
        else:
            self.cancel_button.pack_forget()
        self.status_var.set(label)
        self._reset_progress(start=True)
        threading.Thread(target=self._worker, args=(function,), daemon=True).start()

    def _worker(self, function) -> None:
        try:
            self.events.put(("ok", function()))
        except OperationCancelled:
            self.events.put(("cancelled", None))
        except Exception as exc:
            self.events.put(("error", exc))

    def _worker_progress(self, label: str, value: int, total: int) -> None:
        self.events.put(("progress", (label, value, total)))

    def _worker_cancelled(self) -> bool:
        return self.cancel_event is not None and self.cancel_event.is_set()

    def _cancel_current(self) -> None:
        if self.cancel_event is not None:
            self.cancel_event.set()
            self.cancel_button.configure(state="disabled")
            self.status_var.set("正在取消…")

    def _finish_background(self) -> None:
        self.busy = False
        self.cancel_event = None
        self.scan_button.configure(state="normal")
        self.cancel_button.pack_forget()
        self.cancel_button.configure(state="normal")
        self._reset_progress()

    def _reset_progress(self, start: bool = False) -> None:
        self.progress.stop()
        self.progress.set(0)
        self.progress.configure(mode="indeterminate" if start else "determinate")
        if start:
            if not self.progress.winfo_ismapped():
                self.progress.pack(side="left", padx=(0, 14), before=self.execute_btn)
            self.progress.start()
        else:
            self.progress.pack_forget()

    def _poll_events(self) -> None:
        try:
            while True:
                kind, payload = self.events.get_nowait()
                if kind == "progress":
                    label, value, total = payload
                    maximum = max(total, 1)
                    self.progress.stop()
                    self.progress.configure(mode="determinate")
                    self.progress.set(min(value / maximum, 1.0))
                    percent = min(99, value * 100 // maximum)
                    self.status_var.set(f"{label} {percent}%")
                    continue
                self._finish_background()
                if kind == "error":
                    self.status_var.set("操作失败")
                    messagebox.showerror("错误", str(payload))
                elif kind == "cancelled":
                    self.status_var.set("已取消")
                else:
                    callback, value = payload
                    callback(value)
        except queue.Empty:
            pass
        self.after(100, self._poll_events)

    # ------------------------------------------------------------------ 扫描

    def _scan(self) -> None:
        folder = Path(self.folder_var.get()).expanduser()
        recursive = self.recursive_var.get()
        include_hidden = self.hidden_var.get()
        self._run_background("正在扫描…", lambda: (self._show_scan, (folder, self.engine.scan(folder, recursive, include_hidden))))

    def _show_scan(self, payload) -> None:
        folder, files = payload
        root = folder.resolve()
        self.scan_root = root
        self.files = files
        self.matched_files = None
        self.actions = []
        self.dup_result = None
        self.execute_btn.configure(state="disabled")
        rows = []
        total = 0
        counts: Counter[str] = Counter()
        for path in files:
            size, modified_ts = self._stat_values(path)
            if size is not None:
                total += size
            counts[path.suffix.casefold()] += 1
            rows.append(
                PreviewRow(
                    status="文件",
                    source=self._relative(path),
                    destination="",
                    file_type=file_type_label(path),
                    size_text=format_size(size) if size is not None else "—",
                    modified=format_modified(modified_ts),
                    folder=self._folder_text(path),
                    size_value=size if size is not None else -1,
                    modified_ts=modified_ts or 0.0,
                )
            )
        self._populate_tree(rows)
        type_options: list[tuple[str, str]] = []
        for extension, count in sorted(counts.items(), key=lambda item: (item[0] == "", item[0])):
            name = extension or "无扩展名"
            type_options.append((f"{name} ({count})", extension))
        self.search_type_picker.set_options(type_options)
        self.dup_type_picker.set_options(type_options)
        note = self._truncation_note(len(files))
        self.status_var.set(f"已扫描 {len(files)} 个文件，共 {format_size(total)}{note}")

    # ------------------------------------------------------------------ 预览与执行

    def _show_actions(self, actions: list[Action]) -> None:
        self.actions = actions
        rows = []
        for action in actions:
            try:
                destination = str(action.destination.relative_to(self.scan_root)) if self.scan_root else str(action.destination)
            except ValueError:
                destination = str(action.destination)
            target = action.destination if action.destination.exists() else action.source
            size, modified_ts = self._stat_values(target)
            if action.status == STATUS_FAILED:
                tag = "failed"
            elif action.status in {STATUS_SUCCESS, STATUS_UNDONE}:
                tag = "success"
            else:
                tag = "pending"
            rows.append(
                PreviewRow(
                    status=action.status,
                    source=self._relative(action.source),
                    destination=destination,
                    file_type=file_type_label(target),
                    size_text=format_size(size) if size is not None else "—",
                    modified=format_modified(modified_ts),
                    folder=self._folder_text(action.source),
                    size_value=size if size is not None else -1,
                    modified_ts=modified_ts or 0.0,
                    tags=(tag,),
                )
            )
        self._populate_tree(rows)
        self.execute_btn.configure(state="normal" if actions else "disabled")
        self.status_var.set(f"预览包含 {len(actions)} 项操作；请确认后执行")

    def _execute(self) -> None:
        if not self.actions:
            return
        if not messagebox.askyesno("确认执行", f"即将执行 {len(self.actions)} 项操作。是否继续？"):
            return
        actions = list(self.actions)
        log_dir = self._current_root() / ".file_organizer_logs"
        self._run_background("正在执行…", lambda: (self._show_results, self.engine.execute(actions, log_dir)))

    def _show_results(self, result) -> None:
        actions, log_path = result
        self.last_log = log_path
        self.dup_result = None
        self._show_actions(actions)
        self.actions = []
        self.execute_btn.configure(state="disabled")
        succeeded = sum(item.status == STATUS_SUCCESS for item in actions)
        failed = len(actions) - succeeded
        self.status_var.set(f"执行完成：成功 {succeeded}，失败 {failed}")
        messagebox.showinfo("完成", f"成功：{succeeded}\n失败：{failed}\n日志：{log_path or '无'}")
        self._scan()

    # ------------------------------------------------------------------ 树与通用工具

    def _clear_tree(self) -> None:
        self._tree_generation += 1
        self._preview_rows = []
        self.tree.delete(*self.tree.get_children())

    def _populate_tree(self, rows: list[PreviewRow]) -> None:
        """保存完整行数据并分批渲染；排序或切换字段时不必重新计算。"""
        self._preview_rows = list(rows)
        self._render_preview()

    def _render_preview(self) -> None:
        self._tree_generation += 1
        generation = self._tree_generation
        self.tree.delete(*self.tree.get_children())
        rows = self._preview_rows
        if self._sort_column:
            rows = sort_preview_rows(rows, self._sort_column, self._sort_desc)
        limited = rows[:MAX_PREVIEW_ROWS]
        nodes: dict[str, str] = {}

        def insert_from(index: int) -> None:
            if generation != self._tree_generation:
                return
            for row in limited[index:index + TREE_CHUNK_SIZE]:
                parent = nodes.get(row.parent_token, "") if row.parent_token else ""
                values = tuple(row.value(key) for key in COLUMN_KEYS)
                iid = self.tree.insert(parent, "end", values=values, tags=row.tags)
                if row.token:
                    nodes[row.token] = iid
            next_index = index + TREE_CHUNK_SIZE
            if next_index < len(limited):
                self.after(1, insert_from, next_index)

        insert_from(0)

    def _display_columns(self) -> tuple[str, ...]:
        visible = self._visible_columns | set(FIXED_COLUMNS)
        return tuple(key for key in COLUMN_KEYS if key in visible)

    def _sort_preview(self, column: str) -> None:
        """点击列名：第一次升序，再点一次降序。"""
        if column not in COLUMN_KEYS:
            return
        if self._sort_column == column:
            self._sort_desc = not self._sort_desc
        else:
            self._sort_column = column
            self._sort_desc = False
        self._refresh_headings()
        self._render_preview()

    def _refresh_headings(self) -> None:
        for key in COLUMN_KEYS:
            title = COLUMN_TITLES[key]
            if key == self._sort_column:
                title = f"{title} {'▼' if self._sort_desc else '▲'}"
            self.tree.heading(key, text=title)

    # ------------------------------------------------------------------ 显示字段

    def _toggle_column_picker(self) -> None:
        popup = self._column_popup
        if popup is not None and popup.winfo_exists():
            self._close_column_picker()
            return
        self._open_column_picker()

    def _open_column_picker(self) -> None:
        popup = ctk.CTkToplevel(self)
        self._column_popup = popup
        popup.title("显示字段")
        popup.configure(fg_color=CARD_BG)
        popup.transient(self)
        popup.resizable(False, False)

        body = ctk.CTkFrame(popup, corner_radius=0, fg_color=CARD_BG)
        body.pack(fill="both", expand=True, padx=16, pady=(14, 12))
        label(body, "选择预览表显示的字段", size=13, weight="bold").pack(anchor="w")
        label(
            body,
            "「原文件」固定显示；点击列名可切换升序 / 降序。列较多时可横向滚动，或拖动列边界调整宽度。",
            size=11,
            color=TEXT_SECONDARY,
            wraplength=300,
        ).pack(anchor="w", pady=(4, 10))

        grid = ctk.CTkFrame(body, corner_radius=0, fg_color="transparent")
        grid.pack(fill="x")
        self._column_vars = {}
        for index, key in enumerate(COLUMN_KEYS):
            variable = tk.BooleanVar(value=key in self._visible_columns or key in FIXED_COLUMNS)
            self._column_vars[key] = variable
            widget = checkbox(grid, COLUMN_TITLES[key], variable, command=self._on_column_toggle)
            if key in FIXED_COLUMNS:
                widget.configure(state="disabled")
            widget.grid(row=index // 2, column=index % 2, sticky="w", padx=(0, 18), pady=3)
        grid.columnconfigure(0, weight=1)
        grid.columnconfigure(1, weight=1)

        footer = ctk.CTkFrame(body, corner_radius=0, fg_color="transparent")
        footer.pack(fill="x", pady=(12, 0))
        RoundedButton(footer, text="默认", variant="link", padx=8, pady=4, command=self._reset_columns).pack(side="left")
        RoundedButton(footer, text="全部显示", variant="link", padx=8, pady=4, command=self._show_all_columns).pack(side="left", padx=(2, 0))
        RoundedButton(footer, text="完成", variant="primary", padx=18, pady=6, command=self._close_column_picker).pack(side="right")

        popup.protocol("WM_DELETE_WINDOW", self._close_column_picker)
        popup.bind("<Escape>", lambda _event: self._close_column_picker())
        popup.update_idletasks()
        width = max(330, popup.winfo_reqwidth())
        height = popup.winfo_reqheight()
        x = self.column_button.winfo_rootx() + self.column_button.winfo_width() - width
        y = self.column_button.winfo_rooty() + self.column_button.winfo_height() + 6
        screen_w = popup.winfo_screenwidth()
        screen_h = popup.winfo_screenheight()
        popup.geometry(
            f"{width}x{height}+{max(12, min(x, screen_w - width - 12))}+{max(12, min(y, screen_h - height - 48))}"
        )
        popup.after(60, popup.focus_force)

    def _on_column_toggle(self) -> None:
        visible = {key for key, variable in self._column_vars.items() if variable.get()}
        self._apply_visible_columns(visible)

    def _apply_visible_columns(self, visible: set[str]) -> None:
        self._visible_columns = {key for key in visible if key in COLUMN_KEYS} | set(FIXED_COLUMNS)
        self.tree.configure(displaycolumns=self._display_columns())
        if self._sort_column is not None and self._sort_column not in self._display_columns():
            # 排序字段被隐藏后恢复原始顺序，避免表格看起来“无缘无故”是乱的。
            self._sort_column = None
            self._sort_desc = False
            self._refresh_headings()
            self._render_preview()
        save_visible_columns(self._visible_columns)

    def _reset_columns(self) -> None:
        for key, variable in self._column_vars.items():
            variable.set(key in DEFAULT_VISIBLE or key in FIXED_COLUMNS)
        self._on_column_toggle()

    def _show_all_columns(self) -> None:
        for variable in self._column_vars.values():
            variable.set(True)
        self._on_column_toggle()

    def _close_column_picker(self) -> None:
        popup = self._column_popup
        self._column_popup = None
        if popup is not None and popup.winfo_exists():
            popup.destroy()

    @staticmethod
    def _truncation_note(count: int) -> str:
        if count > MAX_PREVIEW_ROWS:
            return f"（结果较多，仅显示前 {MAX_PREVIEW_ROWS} 行）"
        return ""

    def _relative(self, path: Path) -> str:
        if self.scan_root is not None:
            try:
                return str(path.relative_to(self.scan_root))
            except ValueError:
                pass
        return str(path)

    def _file_size_text(self, path: Path) -> str:
        try:
            return format_size(path.stat().st_size)
        except OSError:
            return "—"

    @staticmethod
    def _stat_values(path: Path) -> tuple[int | None, float | None]:
        """一次 stat 同时取大小和修改时间；取不到时返回 (None, None)。"""
        try:
            info = path.stat()
        except OSError:
            return None, None
        return info.st_size, info.st_mtime

    def _folder_text(self, path: Path) -> str:
        """文件所在的文件夹（相对工作目录，根目录显示为「.」）。"""
        parent = path.parent
        if self.scan_root is not None:
            try:
                relative = parent.relative_to(self.scan_root)
            except ValueError:
                return str(parent)
            text = str(relative)
            return text if text not in {"", "."} else "."
        return str(parent)

    def _current_root(self) -> Path:
        if self.scan_root is not None:
            return self.scan_root
        return Path(self.folder_var.get()).expanduser().resolve()

    def _ensure_files(self) -> bool:
        if not self.files:
            messagebox.showinfo("提示", "请先扫描一个包含文件的目录。")
            return False
        return True

    # ------------------------------------------------------------------ 输入解析

    @staticmethod
    def _optional_float(value: str, label: str) -> float | None:
        if not value.strip():
            return None
        try:
            number = float(value)
        except ValueError as exc:
            raise ValueError(f"{label}请输入数字") from exc
        if number < 0:
            raise ValueError(f"{label}不能为负数")
        return number

    def _resolve_modified_range(self) -> tuple[date | None, date | None]:
        preset = self.time_preset_var.get()
        today = date.today()
        if preset == "全部时间":
            return None, None
        if preset == "今天":
            return today, today
        if preset == "最近7天":
            return today - timedelta(days=6), today
        if preset == "最近30天":
            return today - timedelta(days=29), today
        if preset == "本月":
            return today.replace(day=1), today
        start = self._optional_date(self.search_date_from_var.get(), "开始日期")
        end = self._optional_date(self.search_date_to_var.get(), "结束日期")
        if start and end and start > end:
            raise ValueError("开始日期不能晚于结束日期")
        return start, end

    @staticmethod
    def _optional_date(value: str, label: str) -> date | None:
        if not value.strip():
            return None
        try:
            return datetime.strptime(value.strip(), "%Y-%m-%d").date()
        except ValueError as exc:
            raise ValueError(f"{label}格式应为 YYYY-MM-DD") from exc


def main() -> None:
    FileOrganizerApp().mainloop()


if __name__ == "__main__":
    main()
