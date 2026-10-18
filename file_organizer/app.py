from __future__ import annotations

import queue
import threading
import tkinter as tk
from collections import Counter
from datetime import date, datetime, timedelta
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from .core import (
    STATUS_FAILED,
    STATUS_SUCCESS,
    STATUS_UNDONE,
    Action,
    OrganizerEngine,
)
from .duplicates import OperationCancelled
from .tabs import DuplicatesTabMixin, HistoryTabMixin, OrganizeTabMixin, RenameTabMixin
from .theme import configure_styles
from .utils import format_size
from .widgets import MultiSelectDropdown  # noqa: F401  (供各页签构建时使用)

TREE_CHUNK_SIZE = 500
MAX_PREVIEW_ROWS = 20000


class FileOrganizerApp(RenameTabMixin, OrganizeTabMixin, DuplicatesTabMixin, HistoryTabMixin, tk.Tk):
    def __init__(self) -> None:
        super().__init__()
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

        self.folder_var = tk.StringVar(value=str(Path.home() / "Downloads"))
        self.recursive_var = tk.BooleanVar(value=False)
        self.hidden_var = tk.BooleanVar(value=False)
        self.status_var = tk.StringVar(value="请选择文件夹后扫描")
        self._build_ui()
        self.after(100, self._poll_events)

    def _build_ui(self) -> None:
        configure_styles(self)
        self.configure(bg="#F4F7FB")
        root = ttk.Frame(self, padding=18, style="App.TFrame")
        root.pack(fill="both", expand=True)

        header = ttk.Frame(root, style="App.TFrame")
        header.pack(fill="x", pady=(0, 14))
        ttk.Label(header, text="文件夹整理工具", style="Title.TLabel").pack(anchor="w")
        ttk.Label(header, text="先筛选和预览，再安全地批量重命名、分类或清理重复文件", style="Subtitle.TLabel").pack(anchor="w", pady=(3, 0))

        chooser = ttk.Frame(root, padding=12, style="Card.TFrame")
        chooser.pack(fill="x")
        ttk.Label(chooser, text="工作目录", style="Section.TLabel").pack(side="left", padx=(0, 10))
        ttk.Entry(chooser, textvariable=self.folder_var, style="Modern.TEntry").pack(side="left", fill="x", expand=True, ipady=3)
        ttk.Button(chooser, text="浏览…", command=self._choose_folder).pack(side="left", padx=(8, 0))
        ttk.Checkbutton(chooser, text="包含子文件夹", variable=self.recursive_var).pack(side="left", padx=10)
        ttk.Checkbutton(chooser, text="包含隐藏文件", variable=self.hidden_var).pack(side="left")
        self.scan_button = ttk.Button(chooser, text="扫描文件", style="Primary.TButton", command=self._scan)
        self.scan_button.pack(side="left", padx=(10, 0))

        body = ttk.Panedwindow(root, orient="horizontal")
        body.pack(fill="both", expand=True, pady=10)

        controls = ttk.Frame(body, padding=(0, 0, 10, 0), style="App.TFrame")
        body.add(controls, weight=1)
        controls.columnconfigure(0, weight=1)
        controls.rowconfigure(0, weight=1)
        control_canvas = tk.Canvas(controls, background="#FFFFFF", borderwidth=0, highlightthickness=0)
        control_scrollbar = ttk.Scrollbar(controls, orient="vertical", command=control_canvas.yview)
        control_canvas.configure(yscrollcommand=control_scrollbar.set)
        control_canvas.grid(row=0, column=0, sticky="nsew")
        control_scrollbar.grid(row=0, column=1, sticky="ns")
        control_content = ttk.Frame(control_canvas)
        control_window = control_canvas.create_window((0, 0), window=control_content, anchor="nw")
        control_content.bind("<Configure>", lambda _event: control_canvas.configure(scrollregion=control_canvas.bbox("all")))
        control_canvas.bind("<Configure>", lambda event: control_canvas.itemconfigure(control_window, width=event.width))
        self.bind_all("<MouseWheel>", lambda event: self._scroll_left_panel(event, control_canvas), add="+")

        notebook = ttk.Notebook(control_content)
        notebook.pack(fill="both", expand=True)
        self._build_rename_tab(notebook)
        self._build_organize_tab(notebook)
        self._build_duplicates_tab(notebook)
        self._build_history_tab(notebook)

        preview = ttk.LabelFrame(body, text="文件与操作预览", padding=10, style="Card.TLabelframe")
        body.add(preview, weight=3)
        columns = ("status", "source", "destination", "size")
        self.tree = ttk.Treeview(preview, columns=columns, show="headings", selectmode="extended")
        self.tree.tag_configure("match", foreground="#1D4ED8")
        self.tree.tag_configure("success", foreground="#047857")
        self.tree.tag_configure("failed", foreground="#B91C1C")
        self.tree.tag_configure("pending", foreground="#475569")
        self.tree.tag_configure("dup-hash", foreground="#047857", font=("Microsoft YaHei UI", 10, "bold"))
        self.tree.tag_configure("dup-size", foreground="#B45309", font=("Microsoft YaHei UI", 10, "bold"))
        self.tree.tag_configure("dup-name", foreground="#1D4ED8", font=("Microsoft YaHei UI", 10, "bold"))
        self.tree.tag_configure("keep", foreground="#047857")
        self.tree.tag_configure("candidate", foreground="#B45309")
        headings = {"status": "状态", "source": "原文件", "destination": "目标位置", "size": "大小"}
        widths = {"status": 70, "source": 280, "destination": 330, "size": 90}
        for col in columns:
            self.tree.heading(col, text=headings[col])
            self.tree.column(col, width=widths[col], anchor="w")
        ybar = ttk.Scrollbar(preview, orient="vertical", command=self.tree.yview)
        xbar = ttk.Scrollbar(preview, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=ybar.set, xscrollcommand=xbar.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        ybar.grid(row=0, column=1, sticky="ns")
        xbar.grid(row=1, column=0, sticky="ew")
        preview.rowconfigure(0, weight=1)
        preview.columnconfigure(0, weight=1)

        bottom = ttk.Frame(root, padding=(12, 9), style="Status.TFrame")
        bottom.pack(fill="x")
        ttk.Label(bottom, text="●", style="StatusDot.TLabel").pack(side="left", padx=(0, 7))
        ttk.Label(bottom, textvariable=self.status_var, style="Status.TLabel").pack(side="left")
        self.progress = ttk.Progressbar(bottom, mode="indeterminate", length=160)
        self.progress.pack(side="right", padx=(8, 0))
        self.execute_btn = ttk.Button(bottom, text="执行预览操作", style="Success.TButton", command=self._execute, state="disabled")
        self.execute_btn.pack(side="right")
        self.cancel_button = ttk.Button(bottom, text="取消", command=self._cancel_current)

    # ------------------------------------------------------------------ 选择目录

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
            self.cancel_button.pack(side="right")
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
        self.progress.configure(mode="indeterminate")
        self.progress["value"] = 0
        if start:
            self.progress.start(10)

    def _poll_events(self) -> None:
        try:
            while True:
                kind, payload = self.events.get_nowait()
                if kind == "progress":
                    label, value, total = payload
                    maximum = max(total, 1)
                    self.progress.stop()
                    self.progress.configure(mode="determinate", maximum=maximum)
                    self.progress["value"] = value
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
            try:
                size: int | None = path.stat().st_size
            except OSError:
                size = None
            if size is not None:
                total += size
            counts[path.suffix.casefold()] += 1
            rows.append((("文件", self._relative(path), "", format_size(size) if size is not None else "—"), (), None, None))
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
            size = self._file_size_text(target)
            if action.status == STATUS_FAILED:
                tag = "failed"
            elif action.status in {STATUS_SUCCESS, STATUS_UNDONE}:
                tag = "success"
            else:
                tag = "pending"
            rows.append(((action.status, self._relative(action.source), destination, size), (tag,), None, None))
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
        self.tree.delete(*self.tree.get_children())

    def _populate_tree(self, rows: list[tuple]) -> None:
        """分批填充预览树；rows 元素为 (values, tags, token, parent_token)。"""
        self._tree_generation += 1
        generation = self._tree_generation
        self.tree.delete(*self.tree.get_children())
        limited = rows[:MAX_PREVIEW_ROWS]
        nodes: dict[str, str] = {}

        def insert_from(index: int) -> None:
            if generation != self._tree_generation:
                return
            for values, tags, token, parent_token in limited[index:index + TREE_CHUNK_SIZE]:
                parent = nodes.get(parent_token, "") if parent_token else ""
                iid = self.tree.insert(parent, "end", values=values, tags=tags)
                if token:
                    nodes[token] = iid
            next_index = index + TREE_CHUNK_SIZE
            if next_index < len(limited):
                self.after(1, insert_from, next_index)

        insert_from(0)

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

    def _current_root(self) -> Path:
        if self.scan_root is not None:
            return self.scan_root
        return Path(self.folder_var.get()).expanduser().resolve()

    def _ensure_files(self) -> bool:
        if not self.files:
            messagebox.showinfo("提示", "请先扫描一个包含文件的目录。")
            return False
        return True

    def _scroll_left_panel(self, event, canvas: tk.Canvas) -> str | None:
        target = self.winfo_containing(self.winfo_pointerx(), self.winfo_pointery())
        if target is None or target.winfo_toplevel() is not self:
            return None
        while target is not None and target is not canvas:
            target = getattr(target, "master", None)
        if target is canvas:
            canvas.yview_scroll(-2 if event.delta > 0 else 2, "units")
            return "break"
        return None

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
