"""控件层：基于 CustomTkinter 的统一风格控件与表单元素。

对外暴露两类接口：
- 旧接口保持兼容（``RoundedButton`` / ``RoundedPanel`` / ``SegmentedControl`` /
  ``TabHost`` / ``MultiSelectDropdown``），这样各页签代码无需大改；
- 表单 helper（``label`` / ``hint`` / ``section`` / ``entry`` / ``combo`` /
  ``checkbox`` / ``radio`` / ``textbox``），保证所有页签的输入与选择控件风格一致。
"""

from __future__ import annotations

import tkinter as tk

import customtkinter as ctk

from .core import TYPE_GROUPS
from .theme import (
    ACCENT,
    ACCENT_HOVER,
    BORDER,
    CARD_BG,
    CHECK_BORDER,
    FIELD_BORDER,
    HOVER_BG,
    MUTED_BG,
    SCROLL_THUMB,
    SCROLL_THUMB_ACTIVE,
    SEGMENT_BG,
    SEGMENT_HOVER,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
)
from .theme import font as ui_font

BUTTON_VARIANTS = {
    "primary": {"fill": ACCENT, "hover": ACCENT_HOVER, "text": "#FFFFFF", "border": None},
    "secondary": {"fill": SEGMENT_BG, "hover": SEGMENT_HOVER, "text": TEXT_PRIMARY, "border": None},
    "quiet": {"fill": "transparent", "hover": HOVER_BG, "text": TEXT_PRIMARY, "border": None},
    "link": {"fill": "transparent", "hover": HOVER_BG, "text": ACCENT, "border": None},
    "picker": {"fill": CARD_BG, "hover": HOVER_BG, "text": TEXT_PRIMARY, "border": FIELD_BORDER},
}


def RoundedButton(
    master,
    *,
    text: str = "",
    command=None,
    variant: str = "secondary",
    font=None,
    padx: int = 16,
    pady: int = 8,
    height: int | None = None,
    radius: int = 10,
    align: str = "center",
    surface: str = CARD_BG,
    state: str = "normal",
) -> ctk.CTkButton:
    """统一风格的圆角按钮（CustomTkinter 自带抗锯齿圆角）。

    ``height`` 显式给定时优先使用，方便与输入框/下拉框保持同一高度。
    """
    palette = BUTTON_VARIANTS.get(variant, BUTTON_VARIANTS["secondary"])
    text_font = font if isinstance(font, ctk.CTkFont) else ui_font(12)
    computed_height = int(text_font.metrics("linespace")) + pady * 2
    width = int(text_font.measure(text)) + padx * 2
    return ctk.CTkButton(
        master,
        text=text,
        command=command,
        font=text_font,
        width=max(width, 44),
        height=max(height or computed_height, 28),
        corner_radius=radius,
        fg_color=palette["fill"],
        hover_color=palette["hover"],
        text_color=palette["text"],
        text_color_disabled=MUTED_BG,
        border_width=1 if palette["border"] else 0,
        border_color=palette["border"] or BORDER,
        anchor="w" if align == "w" else "center",
        state=state,
    )


# --------------------------------------------------------------------- 表单控件

def label(master, text: str = "", *, size: int = 12, weight: str = "normal", color: str = TEXT_PRIMARY, **kwargs) -> ctk.CTkLabel:
    """普通文本标签（统一字体与颜色）。"""
    kwargs.setdefault("anchor", "w")
    kwargs.setdefault("justify", "left")
    return ctk.CTkLabel(master, text=text, font=ui_font(size, weight), text_color=color, **kwargs)


def hint(master, text: str, *, wraplength: int = 280, **kwargs) -> ctk.CTkLabel:
    """次要说明文字（小一号、灰色、自动换行）。"""
    return label(master, text, size=11, color=TEXT_SECONDARY, wraplength=wraplength, **kwargs)


def section(master, title: str, *, fill: str = "x", expand: bool = False, pady=0, padx=0) -> ctk.CTkFrame:
    """带标题的白色圆角卡片；返回内容容器，直接把子控件放进去即可。"""
    card = ctk.CTkFrame(master, corner_radius=12, fg_color=CARD_BG, border_width=1, border_color=BORDER)
    card.pack(fill=fill, expand=expand, pady=pady, padx=padx)
    ctk.CTkLabel(card, text=title, font=ui_font(12, "bold"), text_color=TEXT_PRIMARY, anchor="w").pack(fill="x", padx=12, pady=(10, 0))
    body = ctk.CTkFrame(card, corner_radius=0, fg_color="transparent")
    body.pack(fill="both", expand=True, padx=12, pady=(6, 10))
    body.card = card
    return body


def _merge(defaults: dict, width, kwargs: dict) -> dict:
    options = dict(defaults)
    if width:
        options["width"] = max(64, int(width) * 9 + 24)
    options.update(kwargs)
    return options


# 所有输入/选择控件共用同一套尺寸，保证各页签观感一致。
FIELD_HEIGHT = 32
FIELD_RADIUS = 8


def entry(master, *, textvariable=None, width=None, **kwargs) -> ctk.CTkEntry:
    """统一样式的输入框；``width`` 传大约的字符数，会自动换算成像素。"""
    options = _merge(
        {
            "corner_radius": FIELD_RADIUS,
            "height": FIELD_HEIGHT,
            "border_width": 1,
            "border_color": FIELD_BORDER,
            "fg_color": CARD_BG,
            "text_color": TEXT_PRIMARY,
            "font": ui_font(12),
        },
        width,
        kwargs,
    )
    return ctk.CTkEntry(master, textvariable=textvariable, **options)


class SeamlessComboBox(ctk.CTkComboBox):
    """边框左右连续的只读下拉框。

    CustomTkinter 默认把“箭头区”的边框画成 ``button_color``（白底），
    于是 1px 描边在箭头处断掉，看起来像两个拼起来的控件。这里在每次
    重绘后把右侧描边/底色改回与左侧一致，保证是一个完整的圆角框。
    """

    def _draw(self, no_color_updates: bool = False) -> None:
        super()._draw(no_color_updates)
        if not self._canvas.winfo_exists():
            return
        self._canvas.itemconfig(
            "border_parts_right",
            outline=self._apply_appearance_mode(self._border_color),
            fill=self._apply_appearance_mode(self._border_color),
        )
        self._canvas.itemconfig(
            "inner_parts_right",
            outline=self._apply_appearance_mode(self._fg_color),
            fill=self._apply_appearance_mode(self._fg_color),
        )


def combo(master, *, variable=None, values=(), width=None, **kwargs) -> ctk.CTkComboBox:
    """统一样式的下拉选择框（只读，可选择但不可输入）。

    默认只有右侧箭头响应点击，这里让整个控件都可点击展开。
    """
    options = _merge(
        {
            "corner_radius": FIELD_RADIUS,
            "height": FIELD_HEIGHT,
            "border_width": 1,
            "border_color": FIELD_BORDER,
            "fg_color": CARD_BG,
            "button_color": CARD_BG,
            "button_hover_color": HOVER_BG,
            "dropdown_fg_color": CARD_BG,
            "dropdown_hover_color": HOVER_BG,
            "dropdown_text_color": TEXT_PRIMARY,
            "dropdown_font": ui_font(12),
            "text_color": TEXT_PRIMARY,
            "font": ui_font(12),
        },
        width,
        kwargs,
    )
    widget = SeamlessComboBox(master, variable=variable, values=list(values), state="readonly", **options)
    bind_combo_toggle(widget)
    return widget


def bind_combo_toggle(widget: ctk.CTkComboBox) -> None:
    """让下拉框整块可点击：单击文字区域同样展开/收起列表。"""

    def toggle(_event=None):
        menu = widget._dropdown_menu
        if menu.is_open():
            menu.close()
        elif widget.cget("state") != "disabled":
            widget._open_dropdown_menu()

    widget.bind("<Button-1>", toggle)


def checkbox(master, text: str, variable, **kwargs) -> ctk.CTkCheckBox:
    """统一样式的复选框（主题蓝，选中显示标准对勾）。"""
    options = _merge(
        {
            "font": ui_font(12),
            "text_color": TEXT_PRIMARY,
            "fg_color": ACCENT,
            "hover_color": ACCENT_HOVER,
            "border_color": CHECK_BORDER,
            "checkmark_color": "#FFFFFF",
            "corner_radius": 6,
            "border_width": 1,
            "checkbox_width": 20,
            "checkbox_height": 20,
            "text_color_disabled": MUTED_BG,
        },
        None,
        kwargs,
    )
    return ctk.CTkCheckBox(master, text=text, variable=variable, **options)


def radio(master, text: str, variable, value, **kwargs) -> ctk.CTkRadioButton:
    """统一样式的单选框（主题蓝圆点）。"""
    options = _merge(
        {
            "font": ui_font(12),
            "text_color": TEXT_PRIMARY,
            "fg_color": ACCENT,
            "hover_color": ACCENT_HOVER,
            "border_color": CHECK_BORDER,
            "radiobutton_width": 20,
            "radiobutton_height": 20,
            "border_width_unchecked": 1,
            "border_width_checked": 6,
        },
        None,
        kwargs,
    )
    return ctk.CTkRadioButton(master, text=text, variable=variable, value=value, **options)


def textbox(master, *, height: int = 160, **kwargs) -> ctk.CTkTextbox:
    """统一样式的多行文本框。"""
    options = _merge(
        {
            "corner_radius": 8,
            "border_width": 1,
            "border_color": FIELD_BORDER,
            "fg_color": CARD_BG,
            "text_color": TEXT_PRIMARY,
            "font": ui_font(12),
            "scrollbar_button_color": SCROLL_THUMB,
            "scrollbar_button_hover_color": SCROLL_THUMB_ACTIVE,
        },
        None,
        kwargs,
    )
    options["height"] = height
    return ctk.CTkTextbox(master, **options)


def scrollbar(master, *, orientation: str = "vertical", command=None, **kwargs) -> ctk.CTkScrollbar:
    """统一样式的滚动条（配合 Treeview 等标准控件使用）。"""
    options = {
        "orientation": orientation,
        "command": command,
        "fg_color": "transparent",
        "button_color": SCROLL_THUMB,
        "button_hover_color": SCROLL_THUMB_ACTIVE,
    }
    options.update(kwargs)
    return ctk.CTkScrollbar(master, **options)


# --------------------------------------------------------------------- 复合控件

class SegmentedControl(ctk.CTkSegmentedButton):
    """macOS 风格分段控制器，用于替代 Notebook 页签。

    CustomTkinter 的分段控件内部是等宽列、且宽度固定，需要按文字实际
    宽度算出一个不会裁切文字的尺寸。
    """

    def __init__(self, master, *, options=(), command=None, bg: str = CARD_BG, font=None, padx: int = 12, height: int = 34, radius: int = 9) -> None:
        self._label_font = font or ui_font(12)
        super().__init__(
            master,
            values=list(options) or [""],
            command=self._on_change,
            font=self._label_font,
            width=self._measure_width(options),
            height=height,
            corner_radius=radius,
            border_width=2,
            fg_color=SEGMENT_BG,
            selected_color=CARD_BG,
            selected_hover_color=CARD_BG,
            unselected_color=SEGMENT_BG,
            unselected_hover_color=SEGMENT_HOVER,
            text_color=TEXT_PRIMARY,
            dynamic_resizing=False,
        )
        self._labels: list[str] = list(options)
        self._callback = command
        self.index = -1
        self._suppress_change = False
        if self._labels:
            self.select(0, notify=False)

    def _measure_width(self, labels) -> int:
        widest = max((self._label_font.measure(item) for item in labels), default=48) + 34
        return int(widest) * max(len(labels), 1) + 8

    def _on_change(self, value: str) -> None:
        if self._suppress_change or value not in self._labels:
            return
        self.index = self._labels.index(value)
        if self._callback is not None:
            self._callback(self.index)

    def set_options(self, options: list[str]) -> None:
        self._labels = list(options)
        super().configure(values=self._labels or [""], width=self._measure_width(self._labels))
        if self._labels:
            self.select(self.index if 0 <= self.index < len(self._labels) else 0, notify=False)
        else:
            self.index = -1

    def select(self, index: int, notify: bool = False) -> None:
        if not self._labels:
            return
        index = max(0, min(index, len(self._labels) - 1))
        self.index = index
        self._suppress_change = not notify
        try:
            super().set(self._labels[index])
        finally:
            self._suppress_change = False
        if notify and self._callback is not None:
            self._callback(index)


class TabHost(ctk.CTkFrame):
    """带分段控制器的页签容器，接口与 Notebook.add 保持兼容。"""

    def __init__(self, master, *, surface: str = CARD_BG) -> None:
        super().__init__(master, corner_radius=0, fg_color="transparent")
        self.selector = SegmentedControl(self, command=self._on_select, bg=surface)
        self.selector.pack(anchor="w", pady=(0, 14))
        self.frames: list[tk.Widget] = []
        self.titles: list[str] = []
        self.index = -1

    def add(self, frame, text: str | None = None) -> None:
        self.frames.append(frame)
        self.titles.append(text or f"页签 {len(self.frames)}")
        self.selector.set_options(self.titles)
        self._show(self.index if self.index >= 0 else 0)

    def _on_select(self, index: int) -> None:
        self._show(index)

    def _show(self, index: int) -> None:
        for frame in self.frames:
            frame.pack_forget()
        self.index = index
        self.frames[index].pack(fill="both", expand=True)
        self.selector.select(index)


class RoundedPanel(ctk.CTkFrame):
    """白色圆角卡片容器；内容放进 ``.inner``（保持旧接口，方便各面板使用）。"""

    def __init__(self, master, *, radius: int = 12, fill: str = CARD_BG, border: str | None = BORDER, surface: str = "#F5F5F7", padding=12, inset: int = 4, **kwargs) -> None:
        super().__init__(master, corner_radius=radius, fg_color=fill, border_width=1 if border else 0, border_color=border or BORDER, **kwargs)
        pad_x, pad_y = padding if isinstance(padding, tuple) else (padding, padding)
        self.inner = ctk.CTkFrame(self, corner_radius=0, fg_color="transparent")
        self.inner.pack(fill="both", expand=True, padx=pad_x, pady=pad_y)


class MultiSelectDropdown(ctk.CTkFrame):
    """多选文件类型下拉框：按钮 + 复选列表弹窗。"""

    def __init__(self, master) -> None:
        super().__init__(master, corner_radius=0, fg_color="transparent")
        self.options: list[tuple[str, str]] = []
        self.selected: set[str] = set()
        self.popup: ctk.CTkToplevel | None = None
        self._rows: list[tuple[tk.BooleanVar, str]] = []
        self._list: ctk.CTkScrollableFrame | None = None
        self.button = RoundedButton(
            self,
            text="请先扫描文件  ▾",
            variant="picker",
            align="w",
            padx=12,
            pady=0,
            height=FIELD_HEIGHT,
            radius=FIELD_RADIUS,
            command=self._open,
        )
        self.button.pack(fill="x", expand=True)

    # ------------------------------------------------------------- 外部接口

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

    # ------------------------------------------------------------- 弹窗构建

    def _open(self) -> None:
        if not self.options:
            return
        if self.popup is not None and self.popup.winfo_exists():
            self.popup.deiconify()
            self.popup.lift()
            self.popup.focus_force()
            return
        popup = ctk.CTkToplevel(self)
        self.popup = popup
        popup.title("选择文件类型")
        popup.configure(fg_color=CARD_BG)
        popup.transient(self.winfo_toplevel())
        x = self.button.winfo_rootx()
        y = self.button.winfo_rooty() + self.button.winfo_height() + 2
        width = max(self.button.winfo_width(), 400)
        x = min(x, max(0, popup.winfo_screenwidth() - width - 20))
        popup.geometry(f"{width}x420+{x}+{y}")
        popup.protocol("WM_DELETE_WINDOW", self._close_popup)

        label(popup, "选择一个或多个文件类型", size=13, weight="bold").pack(fill="x", padx=14, pady=(12, 0))

        footer = ctk.CTkFrame(popup, corner_radius=0, fg_color="transparent")
        footer.pack(side="bottom", fill="x", padx=14, pady=(6, 12))
        RoundedButton(footer, text="确定", variant="primary", padx=20, pady=7, command=self._apply).pack(side="right")
        RoundedButton(footer, text="取消", variant="secondary", padx=16, pady=7, command=self._close_popup).pack(side="right", padx=(0, 8))

        quick = ctk.CTkFrame(popup, corner_radius=0, fg_color="transparent")
        quick.pack(fill="x", padx=14, pady=(10, 0))
        actions = ctk.CTkFrame(quick, corner_radius=0, fg_color="transparent")
        actions.pack(fill="x")
        RoundedButton(actions, text="全选", variant="link", padx=10, pady=5, command=lambda: self._set_all(True)).pack(side="left")
        RoundedButton(actions, text="反选", variant="link", padx=10, pady=5, command=self._invert).pack(side="left", padx=2)
        RoundedButton(actions, text="清空", variant="link", padx=10, pady=5, command=lambda: self._set_all(False)).pack(side="left")

        group_map = self._available_groups()
        group_var = tk.StringVar(value=next(iter(group_map), ""))
        groups = ctk.CTkFrame(quick, corner_radius=0, fg_color="transparent")
        groups.pack(fill="x", pady=(10, 0))
        label(groups, "按类别：").pack(side="left")
        combo(groups, variable=group_var, values=tuple(group_map)).pack(side="left", fill="x", expand=True, padx=(6, 0))
        RoundedButton(groups, text="选择类别", variant="primary", padx=12, pady=6, command=lambda: self._select_group(group_map.get(group_var.get(), ()))).pack(side="left", padx=(8, 0))

        list_frame = ctk.CTkFrame(popup, corner_radius=0, fg_color="transparent")
        list_frame.pack(fill="both", expand=True, padx=14, pady=(10, 0))
        visible_rows = min(max(len(self.options), 4), 10)
        self._list = ctk.CTkScrollableFrame(
            list_frame,
            corner_radius=8,
            fg_color=CARD_BG,
            border_width=1,
            border_color=BORDER,
            height=visible_rows * 30 + 8,
            scrollbar_button_color=SCROLL_THUMB,
            scrollbar_button_hover_color=SCROLL_THUMB_ACTIVE,
        )
        self._list.pack(fill="both", expand=True)
        self._rows = []
        for row_label, value in self.options:
            variable = tk.BooleanVar(value=value in self.selected)
            checkbox(self._list, row_label, variable).pack(fill="x", padx=8, pady=3, anchor="w")
            self._rows.append((variable, value))

        popup.bind("<Escape>", lambda _event: self._close_popup())
        popup.bind("<Return>", lambda _event: self._apply())
        popup.update_idletasks()
        height = min(max(popup.winfo_reqheight(), 300), 640)
        y = min(y, max(0, popup.winfo_screenheight() - height - 60))
        popup.geometry(f"{width}x{height}+{x}+{y}")
        popup.lift()
        popup.after(30, popup.focus_force)

    # ------------------------------------------------------------- 选择操作

    def _set_all(self, checked: bool) -> None:
        for variable, _ in self._rows:
            variable.set(checked)

    def _invert(self) -> None:
        for variable, _ in self._rows:
            variable.set(not variable.get())

    def _select_group(self, indices: tuple[int, ...]) -> None:
        wanted = set(indices)
        for position, (variable, _) in enumerate(self._rows):
            variable.set(position in wanted)

    def _apply(self) -> None:
        self.selected = {value for variable, value in self._rows if variable.get()}
        self._update_label()
        self._close_popup()

    def _close_popup(self) -> None:
        if self.popup is not None and self.popup.winfo_exists():
            self.popup.destroy()
        self.popup = None

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

    def _update_label(self) -> None:
        total = len(self.options)
        count = len(self.selected)
        if total == 0:
            text = "未扫描到文件类型  ▾"
        elif count == total:
            text = f"全部类型（{total} 种）  ▾"
        elif count == 0:
            text = "未选择类型  ▾"
        elif count <= 2:
            names = [name.rsplit(" (", 1)[0] for name, value in self.options if value in self.selected]
            text = f"{', '.join(names)}  ▾"
        else:
            text = f"已选择 {count} 种类型  ▾"
        self.button.configure(text=text)
