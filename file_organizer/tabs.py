from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox

import customtkinter as ctk

from .core import CleanupOptions, OrganizeOptions, RenameOptions, SearchOptions, TYPE_GROUPS
from .duplicates import DuplicateOptions, DuplicateResult, order_group_members
from .utils import format_size
from .widgets import (
    FIELD_HEIGHT,
    MultiSelectDropdown,
    RoundedButton,
    TabHost,
    checkbox,
    combo,
    entry,
    hint,
    label,
    radio,
    section,
    textbox,
)

KIND_DISPLAY = {"name": "文件名相似", "size": "大小接近", "hash": "字节相同"}
KIND_LABELS = (("文件名相似", "name"), ("大小接近", "size"), ("字节相同", "hash"))
KEEPER_LABELS = (
    ("保留最早修改", "oldest"),
    ("保留最新修改", "newest"),
    ("保留路径最短", "shortest-path"),
    ("保留列表第一个", "first"),
)
KEEPER_VALUES = dict(KEEPER_LABELS)


class RenameTabMixin:
    def _build_rename_tab(self, notebook: TabHost) -> None:
        tab = ctk.CTkFrame(notebook, corner_radius=0, fg_color="transparent")
        notebook.add(tab, text="重命名")
        search_box = section(tab, "第 1 步：搜索要重命名的文件")
        self.search_name_var = tk.StringVar()
        self.search_regex_var = tk.BooleanVar()
        self.search_min_var = tk.StringVar()
        self.search_max_var = tk.StringVar()
        self.time_preset_var = tk.StringVar(value="全部时间")
        self.search_date_from_var = tk.StringVar()
        self.search_date_to_var = tk.StringVar()
        label(search_box, "文件名包含/正则").grid(row=0, column=0, sticky="w", pady=3)
        entry(search_box, textvariable=self.search_name_var).grid(row=0, column=1, sticky="ew", pady=3)
        checkbox(search_box, "使用正则", self.search_regex_var).grid(row=1, column=0, columnspan=2, sticky="w", pady=3)
        label(search_box, "扫描到的类型").grid(row=2, column=0, sticky="w", pady=3)
        self.search_type_picker = MultiSelectDropdown(search_box)
        self.search_type_picker.grid(row=2, column=1, sticky="ew", pady=3)
        label(search_box, "大小范围 MB").grid(row=3, column=0, sticky="w", pady=3)
        sizes = ctk.CTkFrame(search_box, corner_radius=0, fg_color="transparent")
        sizes.grid(row=3, column=1, sticky="ew")
        entry(sizes, textvariable=self.search_min_var, width=7).pack(side="left")
        label(sizes, " 至 ").pack(side="left")
        entry(sizes, textvariable=self.search_max_var, width=7).pack(side="left")
        label(search_box, "修改时间").grid(row=4, column=0, sticky="w", pady=3)
        combo(search_box, variable=self.time_preset_var, values=("全部时间", "今天", "最近7天", "最近30天", "本月", "自定义")).grid(row=4, column=1, sticky="ew", pady=3)
        label(search_box, "自定义日期").grid(row=5, column=0, sticky="w", pady=3)
        dates = ctk.CTkFrame(search_box, corner_radius=0, fg_color="transparent")
        dates.grid(row=5, column=1, sticky="ew")
        entry(dates, textvariable=self.search_date_from_var, width=10).pack(side="left")
        label(dates, " 至 ").pack(side="left")
        entry(dates, textvariable=self.search_date_to_var, width=10).pack(side="left")
        RoundedButton(search_box, text="1. 搜索并显示匹配文件", variant="primary", command=self._search_rename_files).grid(row=6, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        hint(search_box, "自定义日期格式：YYYY-MM-DD；可只填写一端。").grid(row=7, column=0, columnspan=2, sticky="w", pady=(4, 0))
        search_box.columnconfigure(1, weight=1)

        rename_box = section(tab, "第 2 步：设置重命名规则", fill="both", expand=True, pady=(10, 0))
        self.prefix_var = tk.StringVar()
        self.suffix_var = tk.StringVar()
        self.find_var = tk.StringVar()
        self.replace_var = tk.StringVar()
        self.regex_var = tk.BooleanVar()
        self.case_var = tk.StringVar(value="keep")
        self.counter_var = tk.BooleanVar()
        self.counter_start_var = tk.IntVar(value=1)
        self.counter_width_var = tk.IntVar(value=3)
        self.new_extension_var = tk.StringVar()
        fields = [("前缀", self.prefix_var), ("后缀（扩展名前）", self.suffix_var), ("查找", self.find_var), ("替换为", self.replace_var), ("新扩展名", self.new_extension_var)]
        for row, (text, variable) in enumerate(fields):
            label(rename_box, text).grid(row=row, column=0, sticky="w", pady=3)
            entry(rename_box, textvariable=variable).grid(row=row, column=1, sticky="ew", pady=3)
        hint(rename_box, "新扩展名留空则保留原扩展名，例如填写 pdf 或 .pdf。").grid(row=5, column=0, columnspan=2, sticky="w")
        checkbox(rename_box, "查找内容使用正则表达式", self.regex_var).grid(row=6, column=0, columnspan=2, sticky="w", pady=3)
        label(rename_box, "大小写").grid(row=7, column=0, sticky="w", pady=3)
        combo(rename_box, variable=self.case_var, values=("keep", "lower", "upper", "title")).grid(row=7, column=1, sticky="ew")
        checkbox(rename_box, "添加序号", self.counter_var).grid(row=8, column=0, sticky="w", pady=3)
        counter = ctk.CTkFrame(rename_box, corner_radius=0, fg_color="transparent")
        counter.grid(row=8, column=1, sticky="ew")
        label(counter, "起始").pack(side="left")
        entry(counter, textvariable=self.counter_start_var, width=6).pack(side="left", padx=4)
        label(counter, "位数").pack(side="left")
        entry(counter, textvariable=self.counter_width_var, width=4).pack(side="left", padx=4)
        RoundedButton(rename_box, text="2. 生成匹配文件的重命名预览", variant="primary", command=self._preview_rename).grid(row=9, column=0, columnspan=2, sticky="ew", pady=(10, 4))
        hint(rename_box, "重名时自动追加 (1)、(2)…").grid(row=10, column=0, columnspan=2, sticky="w")
        rename_box.columnconfigure(1, weight=1)

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
            matches = self.engine.filter_files(self.files, options)
            self.matched_files = matches
            self.actions = []
            self.execute_btn.configure(state="disabled")
            rows = [(("匹配", self._relative(path), "", self._file_size_text(path)), ("match",), None, None) for path in matches]
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
            options = RenameOptions(prefix=self.prefix_var.get(), suffix=self.suffix_var.get(), find=self.find_var.get(), replace=self.replace_var.get(), use_regex=self.regex_var.get(), case=self.case_var.get(), add_counter=self.counter_var.get(), counter_start=self.counter_start_var.get(), counter_width=self.counter_width_var.get(), new_extension=self.new_extension_var.get())
            self._show_actions(self.engine.preview_rename(self.matched_files, options))
        except Exception as exc:
            messagebox.showerror("规则无效", str(exc))


class OrganizeTabMixin:
    def _build_organize_tab(self, notebook: TabHost) -> None:
        tab = ctk.CTkFrame(notebook, corner_radius=0, fg_color="transparent")
        notebook.add(tab, text="分类整理")
        self.mode_var = tk.StringVar(value="type")
        self.other_var = tk.BooleanVar(value=True)
        label(tab, "分类方式").pack(anchor="w")
        modes = (("按文件类型分组", "type"), ("按扩展名", "extension"), ("按文件名关键词", "name"), ("提取文件名的一部分", "extract"), ("按修改年月", "date"), ("按文件大小", "size"))
        for text, value in modes:
            radio(tab, text, self.mode_var, value).pack(anchor="w", pady=2)
        label(tab, "名称规则（每行：关键词 => 子文件夹）").pack(anchor="w", pady=(12, 4))
        self.rules_text = textbox(tab, height=150)
        self.rules_text.pack(fill="both", expand=True)
        self.rules_text.insert("1.0", "发票 => 发票\n合同 => 合同\n截图 => 截图")
        extract_box = section(tab, "文件名提取规则", pady=(8, 0))
        self.extract_pattern_var = tk.StringVar(value=r"^([^_]+)_")
        self.extract_group_var = tk.StringVar(value="1")
        label(extract_box, "正则表达式").grid(row=0, column=0, sticky="w")
        entry(extract_box, textvariable=self.extract_pattern_var).grid(row=0, column=1, sticky="ew", pady=3)
        label(extract_box, "捕获组").grid(row=1, column=0, sticky="w", pady=(4, 0))
        entry(extract_box, textvariable=self.extract_group_var, width=8).grid(row=1, column=1, sticky="w", pady=(4, 0))
        hint(extract_box, "例：项目A_合同.pdf → 提取“项目A”并创建同名子文件夹", wraplength=270).grid(row=2, column=0, columnspan=2, sticky="w", pady=(4, 0))
        extract_box.columnconfigure(1, weight=1)
        checkbox(tab, "未匹配文件放入“其他”", self.other_var).pack(anchor="w", pady=8)
        RoundedButton(tab, text="生成分类预览", variant="primary", command=self._preview_organize).pack(fill="x", pady=4)
        hint(tab, "分类会在所选工作目录内创建子文件夹。").pack(anchor="w", pady=4)

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
        tab = ctk.CTkFrame(notebook, corner_radius=0, fg_color="transparent")
        notebook.add(tab, text="历史")
        hint(tab, "每次成功操作都会生成 JSON 日志。可选择日志撤销对应操作。").pack(anchor="w", pady=(0, 12))
        RoundedButton(tab, text="撤销上一次操作", variant="secondary", command=self._undo_last).pack(fill="x", pady=4)
        RoundedButton(tab, text="选择日志并撤销…", variant="secondary", command=self._undo_choose).pack(fill="x", pady=4)

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
        succeeded = sum(item.status == "已撤销" for item in actions)
        self.status_var.set(f"撤销完成：成功 {succeeded}，失败 {len(actions) - succeeded}")
        self._scan()


class DuplicatesTabMixin:
    def _build_duplicates_tab(self, notebook: TabHost) -> None:
        tab = ctk.CTkFrame(notebook, corner_radius=0, fg_color="transparent")
        notebook.add(tab, text="查重")

        self.dup_name_var = tk.BooleanVar(value=True)
        self.dup_name_thresh_var = tk.DoubleVar(value=0.75)
        self.dup_size_var = tk.BooleanVar(value=True)
        self.dup_size_percent_var = tk.StringVar(value="0")
        self.dup_size_diff_var = tk.StringVar(value="0")
        self.dup_hash_var = tk.BooleanVar(value=True)
        self.dup_min_size_var = tk.StringVar(value="0")
        self.dup_result: DuplicateResult | None = None
        self.dup_kind_vars: dict[str, tk.BooleanVar] = {}
        self.dup_keeper_var = tk.StringVar(value=KEEPER_LABELS[0][0])

        find_box = section(tab, "第 1 步：查找重复或相似文件")

        name_row = ctk.CTkFrame(find_box, corner_radius=0, fg_color="transparent")
        name_row.pack(fill="x", pady=3)
        checkbox(name_row, "文件名相似", self.dup_name_var).pack(side="left")
        label(name_row, "相似度").pack(side="left", padx=(10, 4))
        entry(name_row, textvariable=self.dup_name_thresh_var, width=6).pack(side="left")

        size_row = ctk.CTkFrame(find_box, corner_radius=0, fg_color="transparent")
        size_row.pack(fill="x", pady=3)
        checkbox(size_row, "大小接近", self.dup_size_var).pack(side="left")
        label(size_row, "差异").pack(side="left", padx=(10, 4))
        entry(size_row, textvariable=self.dup_size_percent_var, width=4).pack(side="left")
        label(size_row, "% 或").pack(side="left", padx=4)
        entry(size_row, textvariable=self.dup_size_diff_var, width=6).pack(side="left")
        label(size_row, "字节").pack(side="left", padx=4)

        checkbox(find_box, "字节相同（哈希确认，大文件较慢）", self.dup_hash_var).pack(anchor="w", pady=3)

        label(find_box, "文件类型").pack(anchor="w", pady=(6, 2))
        type_row = ctk.CTkFrame(find_box, corner_radius=0, fg_color="transparent")
        type_row.pack(fill="x")
        self.dup_type_picker = MultiSelectDropdown(type_row)
        self.dup_type_picker.pack(side="left", fill="x", expand=True)
        RoundedButton(type_row, text="只选视频", variant="secondary", padx=12, pady=7, height=FIELD_HEIGHT, command=self._select_video_types).pack(side="left", padx=(6, 0))

        min_row = ctk.CTkFrame(find_box, corner_radius=0, fg_color="transparent")
        min_row.pack(fill="x", pady=(6, 0))
        label(min_row, "最小大小").pack(side="left")
        entry(min_row, textvariable=self.dup_min_size_var, width=8).pack(side="left", padx=4)
        label(min_row, "MB（视频库建议 ≥ 1）").pack(side="left")

        RoundedButton(find_box, text="1. 查找重复/相似文件", variant="primary", command=self._find_duplicates).pack(fill="x", pady=(8, 2))
        hint(find_box, "查找不会修改任何文件；哈希确认只读取文件内容。").pack(anchor="w")

        clean_box = section(tab, "第 2 步：生成清理预览", pady=(10, 0))
        label(clean_box, "参与清理的分组类型").pack(anchor="w")
        kinds_row = ctk.CTkFrame(clean_box, corner_radius=0, fg_color="transparent")
        kinds_row.pack(fill="x", pady=2)
        for kind_label, kind in KIND_LABELS:
            variable = tk.BooleanVar(value=(kind == "hash"))
            self.dup_kind_vars[kind] = variable
            checkbox(kinds_row, kind_label, variable).pack(side="left", padx=(0, 6))
        keeper_row = ctk.CTkFrame(clean_box, corner_radius=0, fg_color="transparent")
        keeper_row.pack(fill="x", pady=(4, 0))
        label(keeper_row, "每组保留").pack(side="left")
        keeper_box = combo(keeper_row, variable=self.dup_keeper_var, values=tuple(label for label, _ in KEEPER_LABELS))
        keeper_box.pack(side="left", fill="x", expand=True, padx=(6, 0))
        keeper_box.bind("<<ComboboxSelected>>", self._on_keeper_changed)
        RoundedButton(clean_box, text="2. 生成清理预览", variant="primary", command=self._preview_duplicate_cleanup).pack(fill="x", pady=(8, 4))
        hint(clean_box, "清理会把“保留”以外的文件移动到 工作目录/重复文件/组N/，可在“历史与撤销”中恢复。").pack(anchor="w")

    def _select_video_types(self) -> None:
        self.dup_type_picker.set_selected(TYPE_GROUPS["视频"])

    def _duplicate_options(self) -> DuplicateOptions:
        if not self.dup_name_var.get() and not self.dup_size_var.get() and not self.dup_hash_var.get():
            raise ValueError("请至少勾选一种查找方式")
        threshold = float(self.dup_name_thresh_var.get())
        if not 0 < threshold <= 1:
            raise ValueError("相似度阈值应在 0 到 1 之间")
        percent = self._optional_float(self.dup_size_percent_var.get(), "大小差异百分比") or 0.0
        diff = self._optional_float(self.dup_size_diff_var.get(), "大小差异字节数") or 0.0
        return DuplicateOptions(
            name_enabled=self.dup_name_var.get(),
            name_threshold=threshold,
            size_enabled=self.dup_size_var.get(),
            size_tolerance_percent=percent,
            size_tolerance_bytes=int(diff),
            hash_enabled=self.dup_hash_var.get(),
        )

    def _duplicate_candidates(self) -> list[Path]:
        minimum = self._optional_float(self.dup_min_size_var.get(), "最小文件大小")
        selected = self.dup_type_picker.selected_values()
        total = len(self.dup_type_picker.options)
        if total and not selected:
            raise ValueError("请至少选择一种文件类型")
        extensions = () if len(selected) == total else selected
        return self.engine.filter_files(self.files, SearchOptions(extensions=extensions, min_size_mb=minimum))

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
        rows = []
        for kind in ("hash", "size", "name"):
            kind_groups = [group for group in result.groups if group.kind == kind]
            for index, group in enumerate(kind_groups, 1):
                label = KIND_DISPLAY[kind]
                rows.append((("分组", f"{label} · 第 {index} 组 · {len(group.members)} 个文件", "", format_size(group.total_size)), (f"dup-{kind}",), None, None))
                size_of = dict(zip(group.members, group.sizes))
                for position, member in enumerate(order_group_members(group.members, keeper)):
                    status = "保留" if position == 0 else "候选"
                    tag = ("keep",) if position == 0 else ("candidate",)
                    rows.append(((status, self._relative(member), "", format_size(size_of.get(member, 0))), tag, None, None))
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
        kinds = tuple(kind for kind, variable in self.dup_kind_vars.items() if variable.get())
        if not kinds:
            messagebox.showerror("无法清理", "请至少选择一种参与清理的分组类型。")
            return
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
