from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox

import customtkinter as ctk

from .core import CleanupOptions, FileEntry, OrganizeOptions, RenameOptions, SearchOptions, STATUS_UNDONE
from .duplicates import DuplicateOptions, DuplicateResult, order_group_members
from .preview import PreviewRow, file_type_label, format_modified
from .utils import format_size
from .widgets import (
    MultiSelectDropdown,
    ROW_PADY,
    RoundedButton,
    TabHost,
    checkbox,
    combo,
    entry,
    form_grid,
    hint,
    label,
    radio,
    section,
    textbox,
)

KIND_DISPLAY = {"name": "文件名相似", "size": "大小接近", "hash": "字节相同"}
CASE_LABELS = (
    ("保持原样", "keep"),
    ("小写", "lower"),
    ("大写", "upper"),
    ("首字母大写", "title"),
)
CASE_VALUES = dict(CASE_LABELS)
KEEPER_LABELS = (
    ("保留最早修改", "oldest"),
    ("保留最新修改", "newest"),
    ("保留路径最短", "shortest-path"),
    ("保留列表第一个", "first"),
)
KEEPER_VALUES = dict(KEEPER_LABELS)


class RenameTabMixin:
    def _build_rename_tab(self, notebook: TabHost) -> None:
        tab = notebook.make_page()
        notebook.add(tab, text="重命名")
        search_box = section(tab, "第 1 步：搜索要重命名的文件")
        self.search_name_var = tk.StringVar()
        self.search_regex_var = tk.BooleanVar()
        self.search_min_var = tk.StringVar()
        self.search_max_var = tk.StringVar()
        self.time_preset_var = tk.StringVar(value="全部时间")
        self.search_date_from_var = tk.StringVar()
        self.search_date_to_var = tk.StringVar()
        label(search_box, "文件名包含/正则").grid(row=0, column=0, sticky="w", pady=ROW_PADY)
        entry(search_box, textvariable=self.search_name_var).grid(row=0, column=1, sticky="ew", pady=ROW_PADY)
        checkbox(search_box, "使用正则", self.search_regex_var).grid(row=1, column=0, columnspan=2, sticky="w", pady=ROW_PADY)
        label(search_box, "文件类型").grid(row=2, column=0, sticky="w", pady=ROW_PADY)
        self.search_type_picker = MultiSelectDropdown(search_box)
        self.search_type_picker.grid(row=2, column=1, sticky="ew", pady=ROW_PADY)
        label(search_box, "大小范围 MB").grid(row=3, column=0, sticky="w", pady=ROW_PADY)
        sizes = ctk.CTkFrame(search_box, corner_radius=0, fg_color="transparent")
        sizes.grid(row=3, column=1, sticky="ew", pady=ROW_PADY)
        entry(sizes, textvariable=self.search_min_var, width=7).pack(side="left")
        label(sizes, " 至 ").pack(side="left")
        entry(sizes, textvariable=self.search_max_var, width=7).pack(side="left")
        label(search_box, "修改时间").grid(row=4, column=0, sticky="w", pady=ROW_PADY)
        combo(search_box, variable=self.time_preset_var, values=("全部时间", "今天", "最近7天", "最近30天", "本月", "自定义")).grid(row=4, column=1, sticky="ew", pady=ROW_PADY)
        label(search_box, "自定义日期").grid(row=5, column=0, sticky="w", pady=ROW_PADY)
        dates = ctk.CTkFrame(search_box, corner_radius=0, fg_color="transparent")
        dates.grid(row=5, column=1, sticky="ew", pady=ROW_PADY)
        entry(dates, textvariable=self.search_date_from_var, width=10).pack(side="left")
        label(dates, " 至 ").pack(side="left")
        entry(dates, textvariable=self.search_date_to_var, width=10).pack(side="left")
        RoundedButton(search_box, text="1. 搜索并显示匹配文件", variant="primary", command=self._search_rename_files).grid(row=6, column=0, columnspan=2, sticky="ew", pady=(10, 2))
        hint(search_box, "自定义日期格式：YYYY-MM-DD；可只填写一端。").grid(row=7, column=0, columnspan=2, sticky="w", pady=(6, 0))
        form_grid(search_box)

        rename_box = section(tab, "第 2 步：设置重命名规则", fill="both", expand=True, pady=(10, 0))
        self.prefix_var = tk.StringVar()
        self.suffix_var = tk.StringVar()
        self.find_var = tk.StringVar()
        self.replace_var = tk.StringVar()
        self.regex_var = tk.BooleanVar()
        self.case_var = tk.StringVar(value=CASE_LABELS[0][0])
        self.counter_var = tk.BooleanVar()
        self.counter_start_var = tk.IntVar(value=1)
        self.counter_width_var = tk.IntVar(value=3)
        self.new_extension_var = tk.StringVar()
        fields = [("前缀", self.prefix_var), ("后缀（扩展名前）", self.suffix_var), ("查找", self.find_var), ("替换为", self.replace_var), ("新扩展名", self.new_extension_var)]
        for row, (text, variable) in enumerate(fields):
            label(rename_box, text).grid(row=row, column=0, sticky="w", pady=ROW_PADY)
            entry(rename_box, textvariable=variable).grid(row=row, column=1, sticky="ew", pady=ROW_PADY)
        hint(rename_box, "新扩展名留空则保留原扩展名，例如填写 pdf 或 .pdf。").grid(row=5, column=0, columnspan=2, sticky="w", pady=(2, 0))
        checkbox(rename_box, "查找内容使用正则表达式", self.regex_var).grid(row=6, column=0, columnspan=2, sticky="w", pady=ROW_PADY)
        label(rename_box, "大小写").grid(row=7, column=0, sticky="w", pady=ROW_PADY)
        combo(rename_box, variable=self.case_var, values=tuple(label for label, _ in CASE_LABELS)).grid(row=7, column=1, sticky="ew", pady=ROW_PADY)
        checkbox(rename_box, "添加序号", self.counter_var).grid(row=8, column=0, sticky="w", pady=ROW_PADY)
        counter = ctk.CTkFrame(rename_box, corner_radius=0, fg_color="transparent")
        counter.grid(row=9, column=1, sticky="ew", pady=ROW_PADY)
        label(counter, "起始").pack(side="left")
        entry(counter, textvariable=self.counter_start_var, width=6).pack(side="left", padx=6)
        label(counter, "位数").pack(side="left", padx=(6, 0))
        entry(counter, textvariable=self.counter_width_var, width=4).pack(side="left", padx=6)
        RoundedButton(rename_box, text="2. 生成匹配文件的重命名预览", variant="primary", command=self._preview_rename).grid(row=10, column=0, columnspan=2, sticky="ew", pady=(12, 2))
        hint(rename_box, "重名时自动追加 (1)、(2)…").grid(row=11, column=0, columnspan=2, sticky="w")
        form_grid(rename_box)

    def _search_rename_files(self) -> None:
        if not self._ensure_files():
            return
        try:
            minimum = self._optional_float(self.search_min_var.get(), "最小文件大小")
            maximum = self._optional_float(self.search_max_var.get(), "最大文件大小")
            if minimum is not None and maximum is not None and minimum > maximum:
                raise ValueError("最小文件大小不能大于最大文件大小")
            selected_types = self.search_type_picker.selected_values()
            all_type_count = len(self.search_type_picker.options)
            extensions = () if len(selected_types) == all_type_count else selected_types
            if not selected_types and all_type_count:
                self.matched_files = []
                self.actions = []
                self.execute_btn.configure(state="disabled")
                self._clear_tree()
                self.status_var.set(f"搜索完成：0 / {len(self.files)} 个文件匹配（未选择文件类型）")
                return
            modified_from, modified_to = self._resolve_modified_range()
            options = SearchOptions(name_pattern=self.search_name_var.get(), use_regex=self.search_regex_var.get(), extensions=extensions, min_size_mb=minimum, max_size_mb=maximum, modified_from=modified_from, modified_to=modified_to)
            matches = self.engine.filter_files(self.file_entries, options)
            self.matched_files = [entry.path for entry in matches]
            self.actions = []
            self.execute_btn.configure(state="disabled")
            rows = []
            for entry in matches:
                path = entry.path
                size, modified_ts = entry.size, entry.mtime
                rows.append(
                    PreviewRow(
                        status="匹配",
                        source=self._relative(path),
                        file_type=file_type_label(path),
                        size_text=format_size(size) if size is not None else "—",
                        modified=format_modified(modified_ts),
                        folder=self._folder_text(path),
                        size_value=size if size is not None else -1,
                        modified_ts=modified_ts or 0.0,
                        tags=("match",),
                    )
                )
            self._populate_tree(rows)
            note = self._truncation_note(len(rows))
            self.status_var.set(f"搜索完成：{len(matches)} / {len(self.files)} 个文件匹配{note}")
        except Exception as exc:
            messagebox.showerror("搜索规则无效", str(exc))

    def _preview_rename(self) -> None:
        if not self._ensure_files():
            return
        if self.matched_files is None:
            messagebox.showinfo("提示", "请先执行第 1 步，搜索要重命名的文件。")
            return
        if not self.matched_files:
            messagebox.showinfo("提示", "当前搜索规则没有匹配任何文件。")
            return
        try:
            options = RenameOptions(prefix=self.prefix_var.get(), suffix=self.suffix_var.get(), find=self.find_var.get(), replace=self.replace_var.get(), use_regex=self.regex_var.get(), case=CASE_VALUES.get(self.case_var.get(), "keep"), add_counter=self.counter_var.get(), counter_start=self.counter_start_var.get(), counter_width=self.counter_width_var.get(), new_extension=self.new_extension_var.get())
            self._show_actions(self.engine.preview_rename(self.matched_files, options))
        except Exception as exc:
            messagebox.showerror("规则无效", str(exc))


class OrganizeTabMixin:
    def _build_organize_tab(self, notebook: TabHost) -> None:
        tab = notebook.make_page()
        notebook.add(tab, text="分类整理")
        self.mode_var = tk.StringVar(value="type")
        self.other_var = tk.BooleanVar(value=True)

        mode_box = section(tab, "第 1 步：选择分类方式")
        modes = (("按文件类型分组", "type"), ("按扩展名", "extension"), ("按文件名关键词", "name"), ("提取文件名的一部分", "extract"), ("按修改年月", "date"), ("按文件大小", "size"))
        for text, value in modes:
            radio(mode_box, text, self.mode_var, value).pack(anchor="w", pady=3)
        checkbox(mode_box, "未匹配的文件放入“其他”", self.other_var).pack(anchor="w", pady=(10, 0))

        rules_box = section(tab, "第 2 步：设置分类规则", fill="both", expand=True, pady=(10, 0))
        label(rules_box, "名称规则（每行：关键词 => 子文件夹）").pack(anchor="w")
        self.rules_text = textbox(rules_box, height=130)
        self.rules_text.pack(fill="both", expand=True, pady=(6, 10))
        self.rules_text.insert("1.0", "发票 => 发票\n合同 => 合同\n截图 => 截图")

        label(rules_box, "文件名提取规则", size=12, weight="bold").pack(anchor="w", pady=(2, 0))
        extract_box = ctk.CTkFrame(rules_box, corner_radius=0, fg_color="transparent")
        extract_box.pack(fill="x", pady=(6, 0))
        self.extract_pattern_var = tk.StringVar(value=r"^([^_]+)_")
        self.extract_group_var = tk.StringVar(value="1")
        label(extract_box, "正则表达式").grid(row=0, column=0, sticky="w", pady=ROW_PADY)
        entry(extract_box, textvariable=self.extract_pattern_var).grid(row=0, column=1, sticky="ew", pady=ROW_PADY)
        label(extract_box, "捕获组").grid(row=1, column=0, sticky="w", pady=ROW_PADY)
        entry(extract_box, textvariable=self.extract_group_var, width=8).grid(row=1, column=1, sticky="w", pady=ROW_PADY)
        hint(extract_box, "例：项目A_合同.pdf → 提取“项目A”并创建同名子文件夹", wraplength=270).grid(row=2, column=0, columnspan=2, sticky="w", pady=(4, 0))
        form_grid(extract_box)

        RoundedButton(rules_box, text="生成分类预览", variant="primary", command=self._preview_organize).pack(fill="x", pady=(14, 2))
        hint(rules_box, "分类会在所选工作目录内创建子文件夹。").pack(anchor="w", pady=(4, 0))

    def _preview_organize(self) -> None:
        if not self._ensure_files():
            return
        rules = []
        for line in self.rules_text.get("1.0", "end").splitlines():
            if "=>" in line:
                key, folder = (part.strip() for part in line.split("=>", 1))
                if key and folder:
                    rules.append((key, folder))
        try:
            options = OrganizeOptions(mode=self.mode_var.get(), name_rules=tuple(rules), extract_pattern=self.extract_pattern_var.get(), extract_group=self.extract_group_var.get().strip() or "1", include_other=self.other_var.get())
            self._show_actions(self.engine.preview_organize(self.files, self._current_root(), options))
        except Exception as exc:
            messagebox.showerror("分类规则无效", str(exc))


class HistoryTabMixin:
    def _build_history_tab(self, notebook: TabHost) -> None:
        tab = notebook.make_page()
        notebook.add(tab, text="历史")
        undo_box = section(tab, "历史与撤销")
        hint(undo_box, "每次成功操作都会生成 JSON 日志，可选择日志撤销对应操作。").pack(anchor="w", pady=(0, 10))
        RoundedButton(undo_box, text="撤销上一次操作", variant="secondary", command=self._undo_last).pack(fill="x", pady=(0, 6))
        RoundedButton(undo_box, text="选择日志并撤销…", variant="secondary", command=self._undo_choose).pack(fill="x")

    def _undo_last(self) -> None:
        log_dir = self._current_root() / ".file_organizer_logs"
        if self.last_log is not None and self.last_log.exists() and self.last_log.parent == log_dir:
            candidate = self.last_log
        else:
            candidate = None
            if log_dir.exists():
                logs = sorted(log_dir.glob("operation_*.json*"), reverse=True)
                candidate = logs[0] if logs else None
        self.last_log = candidate
        if not candidate:
            messagebox.showinfo("提示", "当前目录没有可撤销的操作日志。")
            return
        self._undo(candidate)

    def _undo_choose(self) -> None:
        selected = filedialog.askopenfilename(initialdir=str(self._current_root() / ".file_organizer_logs"), filetypes=(("日志文件", "*.json*"), ("所有文件", "*.*")))
        if selected:
            self._undo(Path(selected))

    def _undo(self, log_path: Path) -> None:
        if not messagebox.askyesno("确认撤销", f"撤销日志中的操作？\n{log_path}"):
            return
        self._run_background("正在撤销…", lambda: (self._show_undo, self.engine.undo(log_path)))

    def _show_undo(self, actions) -> None:
        self._show_actions(actions)
        self.actions = []
        self.dup_result = None
        self.execute_btn.configure(state="disabled")
        succeeded = sum(item.status == STATUS_UNDONE for item in actions)
        self.status_var.set(f"撤销完成：成功 {succeeded}，失败 {len(actions) - succeeded}；点击「扫描文件」可刷新列表")


class DuplicatesTabMixin:
    def _build_duplicates_tab(self, notebook: TabHost) -> None:
        tab = notebook.make_page()
        notebook.add(tab, text="查重")

        self.dup_name_var = tk.BooleanVar(value=True)
        self.dup_name_thresh_var = tk.DoubleVar(value=0.75)
        self.dup_size_var = tk.BooleanVar(value=True)
        self.dup_size_percent_var = tk.StringVar(value="0")
        self.dup_size_diff_var = tk.StringVar(value="0")
        self.dup_hash_var = tk.BooleanVar(value=True)
        self.dup_workers_var = tk.StringVar(value="4")
        self.dup_min_size_var = tk.StringVar()
        self.dup_max_size_var = tk.StringVar()
        self.dup_result: DuplicateResult | None = None
        self.dup_match_label = ""
        self.dup_keeper_var = tk.StringVar(value=KEEPER_LABELS[0][0])

        find_box = section(tab, "第 1 步：查找重复或相似文件")

        # 与重命名页保持同一套栅格：第 0 列放标签/复选框，第 1 列放控件。
        checkbox(find_box, "文件名相似", self.dup_name_var).grid(row=0, column=0, sticky="w", pady=ROW_PADY)
        name_row = ctk.CTkFrame(find_box, corner_radius=0, fg_color="transparent")
        name_row.grid(row=0, column=1, sticky="ew", pady=ROW_PADY)
        label(name_row, "相似度").pack(side="left")
        entry(name_row, textvariable=self.dup_name_thresh_var, width=6).pack(side="left", padx=(6, 0))

        checkbox(find_box, "大小接近", self.dup_size_var).grid(row=1, column=0, sticky="w", pady=ROW_PADY)
        size_row = ctk.CTkFrame(find_box, corner_radius=0, fg_color="transparent")
        size_row.grid(row=1, column=1, sticky="ew", pady=ROW_PADY)
        label(size_row, "差异").pack(side="left")
        entry(size_row, textvariable=self.dup_size_percent_var, width=4).pack(side="left", padx=(6, 0))
        label(size_row, "% 或").pack(side="left", padx=4)
        entry(size_row, textvariable=self.dup_size_diff_var, width=6).pack(side="left")
        label(size_row, "字节").pack(side="left", padx=4)

        hash_row = ctk.CTkFrame(find_box, corner_radius=0, fg_color="transparent")
        hash_row.grid(row=2, column=0, columnspan=2, sticky="ew", pady=ROW_PADY)
        checkbox(hash_row, "字节相同（哈希确认，大文件较慢）", self.dup_hash_var).pack(side="left")
        label(hash_row, "读盘线程").pack(side="left", padx=(16, 4))
        entry(hash_row, textvariable=self.dup_workers_var, width=3).pack(side="left")

        label(find_box, "文件类型").grid(row=3, column=0, sticky="w", pady=ROW_PADY)
        self.dup_type_picker = MultiSelectDropdown(find_box)
        self.dup_type_picker.grid(row=3, column=1, sticky="ew", pady=ROW_PADY)

        label(find_box, "大小范围 MB").grid(row=4, column=0, sticky="w", pady=ROW_PADY)
        dup_sizes = ctk.CTkFrame(find_box, corner_radius=0, fg_color="transparent")
        dup_sizes.grid(row=4, column=1, sticky="ew", pady=ROW_PADY)
        entry(dup_sizes, textvariable=self.dup_min_size_var, width=7).pack(side="left")
        label(dup_sizes, " 至 ").pack(side="left")
        entry(dup_sizes, textvariable=self.dup_max_size_var, width=7).pack(side="left")

        RoundedButton(find_box, text="1. 查找重复/相似文件", variant="primary", command=self._find_duplicates).grid(row=5, column=0, columnspan=2, sticky="ew", pady=(12, 2))
        hint(find_box, "勾选的查找方式会叠加生效：只保留同时满足全部分组。查找只读取文件，不会修改；大小范围留空表示不限制。").grid(row=6, column=0, columnspan=2, sticky="w", pady=(6, 0))
        form_grid(find_box)

        clean_box = section(tab, "第 2 步：生成清理预览", pady=(10, 0))
        keeper_row = ctk.CTkFrame(clean_box, corner_radius=0, fg_color="transparent")
        keeper_row.pack(fill="x", pady=(10, 0))
        label(keeper_row, "每组保留").pack(side="left")
        keeper_box = combo(keeper_row, variable=self.dup_keeper_var, values=tuple(label for label, _ in KEEPER_LABELS), command=self._on_keeper_changed)
        keeper_box.pack(side="left", fill="x", expand=True, padx=(8, 0))
        RoundedButton(clean_box, text="2. 生成清理预览", variant="primary", command=self._preview_duplicate_cleanup).pack(fill="x", pady=(12, 2))
        hint(clean_box, "清理会把“保留”以外的文件移动到 工作目录/重复文件/组N/，可在“历史与撤销”中恢复。").pack(anchor="w")

    def _duplicate_options(self) -> DuplicateOptions:
        if not self.dup_name_var.get() and not self.dup_size_var.get() and not self.dup_hash_var.get():
            raise ValueError("请至少勾选一种查找方式")
        threshold = float(self.dup_name_thresh_var.get())
        if not 0 < threshold <= 1:
            raise ValueError("相似度阈值应在 0 到 1 之间")
        percent = self._optional_float(self.dup_size_percent_var.get(), "大小差异百分比") or 0.0
        diff = self._optional_float(self.dup_size_diff_var.get(), "大小差异字节数") or 0.0
        try:
            workers = int(self.dup_workers_var.get().strip())
        except ValueError as exc:
            raise ValueError("读盘线程请输入整数") from exc
        if not 1 <= workers <= 32:
            raise ValueError("读盘线程应在 1 到 32 之间")
        return DuplicateOptions(
            name_enabled=self.dup_name_var.get(),
            name_threshold=threshold,
            size_enabled=self.dup_size_var.get(),
            size_tolerance_percent=percent,
            size_tolerance_bytes=int(diff),
            hash_enabled=self.dup_hash_var.get(),
            workers=workers,
        )

    def _duplicate_candidates(self) -> list[FileEntry]:
        minimum = self._optional_float(self.dup_min_size_var.get(), "最小文件大小")
        maximum = self._optional_float(self.dup_max_size_var.get(), "最大文件大小")
        if minimum is not None and maximum is not None and minimum > maximum:
            raise ValueError("文件大小范围无效：下限大于上限")
        selected = self.dup_type_picker.selected_values()
        total = len(self.dup_type_picker.options)
        if total and not selected:
            raise ValueError("请至少选择一种文件类型")
        extensions = () if len(selected) == total else selected
        return self.engine.filter_files(self.file_entries, SearchOptions(extensions=extensions, min_size_mb=minimum, max_size_mb=maximum))

    def _current_match_label(self) -> str:
        """当前勾选的查找方式（叠加）文本，用于结果里的分组标题。"""
        parts = [
            KIND_DISPLAY[kind]
            for kind, variable in (("name", self.dup_name_var), ("size", self.dup_size_var), ("hash", self.dup_hash_var))
            if variable.get()
        ]
        return " + ".join(parts) if parts else "重复/相似文件"

    def _find_duplicates(self) -> None:
        if not self._ensure_files():
            return
        try:
            options = self._duplicate_options()
            candidates = self._duplicate_candidates()
        except Exception as exc:
            messagebox.showerror("查找条件无效", str(exc))
            return
        if not candidates:
            messagebox.showinfo("提示", "当前条件没有可查找的文件。")
            return
        self.dup_match_label = self._current_match_label()
        self._run_background(
            "正在查找重复文件…",
            lambda: (
                self._show_duplicate_result,
                self.engine.find_duplicates(candidates, options, progress=self._worker_progress, cancelled=self._worker_cancelled),
            ),
            cancellable=True,
        )

    def _show_duplicate_result(self, result: DuplicateResult) -> None:
        self.dup_result = result
        self.actions = []
        self.execute_btn.configure(state="disabled")
        if not result.groups:
            self._clear_tree()
            self.status_var.set("查找完成：没有找到重复或相似的文件")
            messagebox.showinfo("完成", "没有找到重复或相似的文件。")
            return
        keeper = self._current_keeper()
        match_label = self.dup_match_label or "重复/相似文件"
        rows = []
        for index, group in enumerate(result.groups, 1):
            rows.append(
                PreviewRow(
                    status="分组",
                    source=f"{match_label} · 第 {index} 组 · {len(group.members)} 个文件",
                    size_text=format_size(group.total_size),
                    size_value=group.total_size,
                    tags=(f"dup-{group.kind}",),
                    group=index,
                    is_header=True,
                )
            )
            size_of = dict(zip(group.members, group.sizes))
            for position, member in enumerate(order_group_members(group.members, keeper, group.mtime_of)):
                status = "保留" if position == 0 else "候选"
                tag = ("keep",) if position == 0 else ("candidate",)
                size = size_of.get(member, 0)
                modified_ts = group.mtime_of.get(member)
                rows.append(
                    PreviewRow(
                        status=status,
                        source=self._relative(member),
                        file_type=file_type_label(member),
                        size_text=format_size(size),
                        modified=format_modified(modified_ts),
                        folder=self._folder_text(member),
                        size_value=size,
                        modified_ts=modified_ts or 0.0,
                        tags=tag,
                        group=index,
                    )
                )
        self._populate_tree(rows)
        reclaim = sum(group.reclaimable_bytes for group in result.groups)
        note = self._truncation_note(len(rows))
        self.status_var.set(f"找到 {len(result.groups)} 组重复/相似文件，预计可释放 {format_size(reclaim)}{note}")

    def _current_keeper(self) -> str:
        return KEEPER_VALUES.get(self.dup_keeper_var.get(), "oldest")

    def _on_keeper_changed(self, _event=None) -> None:
        if self.dup_result is not None and self.dup_result.groups:
            self._show_duplicate_result(self.dup_result)

    def _preview_duplicate_cleanup(self) -> None:
        if not self._ensure_files():
            return
        if self.dup_result is None or not self.dup_result.groups:
            messagebox.showinfo("提示", "请先在第 1 步查找重复文件。")
            return
        kinds = tuple(dict.fromkeys(group.kind for group in self.dup_result.groups))
        try:
            options = CleanupOptions(kinds=kinds, keeper=self._current_keeper())
            actions = self.engine.preview_duplicate_cleanup(self.dup_result.groups, self._current_root(), options)
        except Exception as exc:
            messagebox.showerror("清理规则无效", str(exc))
            return
        if not actions:
            messagebox.showinfo("完成", "当前设置没有需要移动的文件。")
            return
        self._show_actions(actions)
