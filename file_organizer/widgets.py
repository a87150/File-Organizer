from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from .core import TYPE_GROUPS


class MultiSelectDropdown(ttk.Frame):
    """Compact multi-select control that opens a list below the button."""

    def __init__(self, master) -> None:
        super().__init__(master)
        self.options: list[tuple[str, str]] = []
        self.selected: set[str] = set()
        self.popup: tk.Toplevel | None = None
        self.button = ttk.Button(self, text="请先扫描文件", style="Picker.TButton", command=self._open)
        self.button.pack(fill="x", expand=True)

    def set_options(self, options: list[tuple[str, str]]) -> None:
        self._close_popup()
        self.options = options
        self.selected = {value for _, value in options}
        self._update_label()

    def set_selected(self, values: set[str]) -> None:
        """按值集合更新选中项（用于“只选视频”等快捷操作）。"""
        available = {value for _, value in self.options}
        self.selected = {value for value in values if value in available}
        self._update_label()

    def selected_values(self) -> tuple[str, ...]:
        return tuple(value for _, value in self.options if value in self.selected)

    def _open(self) -> None:
        if not self.options:
            return
        if self.popup and self.popup.winfo_exists():
            self.popup.deiconify()
            self.popup.lift()
            self.popup.focus_force()
            return
        popup = tk.Toplevel(self)
        self.popup = popup
        popup.title("选择文件类型")
        popup.transient(self.winfo_toplevel())
        popup.configure(bg="#FFFFFF")
        popup.resizable(True, True)
        x = self.button.winfo_rootx()
        y = self.button.winfo_rooty() + self.button.winfo_height() + 2
        width = max(self.button.winfo_width(), 380)
        height = min(430, max(220, 110 + len(self.options) * 25))
        x = min(x, max(0, popup.winfo_screenwidth() - width - 20))
        y = min(y, max(0, popup.winfo_screenheight() - height - 60))
        popup.geometry(f"{width}x{height}+{x}+{y}")
        popup.minsize(380, 260)
        popup.protocol("WM_DELETE_WINDOW", self._close_popup)

        header = ttk.Frame(popup, style="Popup.TFrame", padding=(12, 10))
        header.pack(fill="x")
        ttk.Label(header, text="选择一个或多个文件类型", style="PopupTitle.TLabel").pack(anchor="w")

        list_frame = ttk.Frame(popup, style="Popup.TFrame", padding=(10, 0))
        list_frame.pack(fill="both", expand=True)
        listbox = tk.Listbox(list_frame, selectmode=tk.MULTIPLE, exportselection=False, activestyle="none", borderwidth=0, highlightthickness=1, highlightbackground="#E2E8F0", selectbackground="#2563EB", selectforeground="#FFFFFF", font=("Microsoft YaHei UI", 10))
        scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=listbox.yview)
        listbox.configure(yscrollcommand=scrollbar.set)
        listbox.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        for index, (label, value) in enumerate(self.options):
            listbox.insert("end", label)
            if value in self.selected:
                listbox.selection_set(index)

        quick = ttk.Frame(popup, style="Popup.TFrame", padding=(12, 8))
        quick.pack(fill="x", before=list_frame)
        actions = ttk.Frame(quick, style="Popup.TFrame")
        actions.pack(fill="x")
        ttk.Button(actions, text="全选", style="Link.TButton", command=lambda: listbox.selection_set(0, "end")).pack(side="left")
        ttk.Button(actions, text="反选", style="Link.TButton", command=lambda: self._invert_selection(listbox)).pack(side="left", padx=4)
        ttk.Button(actions, text="清空", style="Link.TButton", command=lambda: listbox.selection_clear(0, "end")).pack(side="left")

        group_map = self._available_groups()
        group_var = tk.StringVar(value=next(iter(group_map), ""))
        groups = ttk.Frame(quick, style="Popup.TFrame")
        groups.pack(fill="x", pady=(8, 0))
        ttk.Label(groups, text="按类别：", style="PopupTitle.TLabel").pack(side="left")
        ttk.Combobox(groups, textvariable=group_var, state="readonly", values=tuple(group_map)).pack(side="left", fill="x", expand=True)
        ttk.Button(groups, text="选择类别", style="Primary.TButton", command=lambda: self._select_group(listbox, group_map.get(group_var.get(), ()))).pack(side="left", padx=(8, 0))

        footer = ttk.Frame(popup, style="Popup.TFrame", padding=10)
        footer.pack(fill="x")
        ttk.Button(footer, text="确定", style="Primary.TButton", command=lambda: self._apply(listbox)).pack(side="right")
        ttk.Button(footer, text="取消", command=self._close_popup).pack(side="right", padx=(0, 8))
        popup.bind("<Escape>", lambda _event: self._close_popup())
        listbox.focus_set()

    def _invert_selection(self, listbox: tk.Listbox) -> None:
        selected = set(listbox.curselection())
        listbox.selection_clear(0, "end")
        for index in range(listbox.size()):
            if index not in selected:
                listbox.selection_set(index)

    def _select_group(self, listbox: tk.Listbox, indices: tuple[int, ...]) -> None:
        listbox.selection_clear(0, "end")
        for index in indices:
            listbox.selection_set(index)
        if indices:
            listbox.see(indices[0])

    def _available_groups(self) -> dict[str, tuple[int, ...]]:
        groups: dict[str, list[int]] = {name: [] for name in TYPE_GROUPS}
        other: list[int] = []
        for index, (_label, extension) in enumerate(self.options):
            for group, extensions in TYPE_GROUPS.items():
                if extension in extensions:
                    groups[group].append(index)
                    break
            else:
                other.append(index)
        result = {
            f"{name}（{len(indices)} 种）": tuple(indices)
            for name, indices in groups.items()
            if indices
        }
        if other:
            result[f"其他（{len(other)} 种）"] = tuple(other)
        return result

    def _apply(self, listbox: tk.Listbox) -> None:
        selected_indices = listbox.curselection()
        self.selected = {self.options[index][1] for index in selected_indices}
        self._update_label()
        self._close_popup()

    def _close_popup(self) -> None:
        if self.popup and self.popup.winfo_exists():
            self.popup.destroy()
        self.popup = None

    def _update_label(self) -> None:
        total = len(self.options)
        count = len(self.selected)
        if total == 0:
            label = "未扫描到文件类型"
        elif count == total:
            label = f"全部类型（{total} 种）  ▾"
        elif count == 0:
            label = "未选择类型  ▾"
        elif count <= 2:
            names = [name.rsplit(" (", 1)[0] for name, value in self.options if value in self.selected]
            label = f"{', '.join(names)}  ▾"
        else:
            label = f"已选择 {count} 种类型  ▾"
        self.button.configure(text=label)
