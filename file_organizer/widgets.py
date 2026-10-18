from __future__ import annotations

import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk

from .core import TYPE_GROUPS
from .theme import FONT_FAMILY


_AA_SAMPLES = 4


def _hex_to_rgb(value: str) -> tuple[int, int, int]:
    value = value.lstrip("#")
    return int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16)


def _blend(base: str, color: str, coverage: float) -> str:
    if coverage >= 0.999:
        return color
    if coverage <= 0.001:
        return base
    base_r, base_g, base_b = _hex_to_rgb(base)
    color_r, color_g, color_b = _hex_to_rgb(color)
    red = round(base_r + (color_r - base_r) * coverage)
    green = round(base_g + (color_g - base_g) * coverage)
    blue = round(base_b + (color_b - base_b) * coverage)
    return f"#{red:02x}{green:02x}{blue:02x}"


def _corner_pixels(radius: int, color: str, base: str) -> list[list[str]]:
    """左上角的抗锯齿像素矩阵（4x4 超采样），其余角通过镜像得到。"""
    matrix: list[list[str]] = []
    total = _AA_SAMPLES * _AA_SAMPLES
    for py in range(radius):
        row: list[str] = []
        for px in range(radius):
            inside = 0
            for i in range(_AA_SAMPLES):
                for j in range(_AA_SAMPLES):
                    sx = px + (i + 0.5) / _AA_SAMPLES
                    sy = py + (j + 0.5) / _AA_SAMPLES
                    if (sx - radius) ** 2 + (sy - radius) ** 2 <= radius * radius:
                        inside += 1
            row.append(_blend(base, color, inside / total))
        matrix.append(row)
    return matrix


def _paint_rounded(image: tk.PhotoImage, width: int, height: int, radius: int, color: str, base: str | None, offset: tuple[int, int] = (0, 0)) -> None:
    """在图像上绘制一个抗锯齿的圆角矩形；base 为圆角外的底色（None 表示实心填充整块）。"""
    ox, oy = offset
    if width <= 0 or height <= 0:
        return
    if base is None:
        image.put(color, to=(ox, oy, ox + width, oy + height))
        return
    radius = max(1, min(radius, width // 2, height // 2))
    if height - 2 * radius > 0:
        image.put(color, to=(ox, oy + radius, ox + width, oy + height - radius))
    if width - 2 * radius > 0:
        image.put(color, to=(ox + radius, oy, ox + width - radius, oy + height))
    corner = _corner_pixels(radius, color, base)

    normal = " ".join("{" + " ".join(row) + "}" for row in corner)
    flipped = " ".join("{" + " ".join(row) + "}" for row in reversed(corner))
    mirrored = " ".join("{" + " ".join(reversed(row)) + "}" for row in corner)
    mirrored_flipped = " ".join("{" + " ".join(reversed(row)) + "}" for row in reversed(corner))
    image.put(normal, to=(ox, oy))
    image.put(mirrored, to=(ox + width - radius, oy))
    image.put(flipped, to=(ox, oy + height - radius))
    image.put(mirrored_flipped, to=(ox + width - radius, oy + height - radius))


def rounded_rect_image(width: int, height: int, radius: int, fill: str, surface: str, border: str | None = None) -> tk.PhotoImage:
    """生成带抗锯齿圆角的矩形图像（纯标准库，无需第三方依赖）。"""
    width = max(int(width), 2)
    height = max(int(height), 2)
    radius = max(1, min(int(radius), width // 2, height // 2))
    image = tk.PhotoImage(width=width, height=height)
    image.put(surface, to=(0, 0, width, height))
    if border:
        _paint_rounded(image, width, height, radius, border, surface)
        inset_radius = max(radius - 1, 1)
        _paint_rounded(image, width - 2, height - 2, inset_radius, fill, border, offset=(1, 1))
    else:
        _paint_rounded(image, width, height, radius, fill, surface)
    return image


class RoundedButton(tk.Canvas):
    """圆角按钮，支持 primary / secondary / quiet / link / picker 变体。"""

    _VARIANTS = {
        "primary": {"fill": "#0071E3", "hover": "#0077ED", "pressed": "#0062C4", "text": "#FFFFFF", "border": ""},
        "secondary": {"fill": "#E8E8ED", "hover": "#DEDEE3", "pressed": "#D2D2D7", "text": "#1D1D1F", "border": ""},
        "quiet": {"fill": "", "hover": "#F2F2F7", "pressed": "#E8E8ED", "text": "#1D1D1F", "border": ""},
        "link": {"fill": "", "hover": "#EAF3FF", "pressed": "#DBEAFF", "text": "#0071E3", "border": ""},
        "picker": {"fill": "#FFFFFF", "hover": "#F7F7F9", "pressed": "#F2F2F7", "text": "#1D1D1F", "border": "#D2D2D7"},
    }
    _DISABLED_FILL = "#E8E8ED"
    _DISABLED_TEXT = "#AEAEB2"

    def __init__(
        self,
        master,
        *,
        text: str = "",
        command=None,
        variant: str = "secondary",
        font=None,
        padx: int = 16,
        pady: int = 8,
        radius: int = 10,
        align: str = "center",
        surface: str = "#FFFFFF",
        state: str = "normal",
    ) -> None:
        super().__init__(master, highlightthickness=0, bd=0, bg=surface, cursor="hand2" if state != "disabled" else "arrow")
        self._font = tkfont.Font(font=font or (FONT_FAMILY, 10))
        self._variant = variant if variant in self._VARIANTS else "secondary"
        self._command = command
        self._padx = padx
        self._pady = pady
        self._radius = radius
        self._align = align
        self._surface = surface
        self._state = state
        self._text = text
        self._hovered = False
        self._pressed = False
        self._images: dict[tuple, tk.PhotoImage] = {}
        self._apply_size()
        self.bind("<Configure>", lambda _event: self._draw())
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<ButtonPress-1>", self._on_press)
        self.bind("<ButtonRelease-1>", self._on_release)

    def _apply_size(self) -> None:
        width = self._font.measure(self._text) + self._padx * 2
        height = self._font.metrics("linespace") + self._pady * 2
        super().configure(width=max(width, 44), height=max(height, 28))

    def configure(self, cnf=None, **kw):
        redraw = False
        if "text" in kw:
            self._text = kw.pop("text")
            redraw = True
        if "state" in kw:
            self._state = kw.pop("state")
            super().configure(cursor="arrow" if self._state == "disabled" else "hand2")
            redraw = True
        if "command" in kw:
            self._command = kw.pop("command")
        result = super().configure(cnf, **kw)
        if redraw:
            self._apply_size()
            self._draw()
        return result

    config = configure

    def _on_enter(self, _event) -> None:
        self._hovered = True
        self._draw()

    def _on_leave(self, _event) -> None:
        self._hovered = False
        self._pressed = False
        self._draw()

    def _on_press(self, _event) -> None:
        if self._state == "disabled":
            return
        self._pressed = True
        self._draw()

    def _on_release(self, _event) -> None:
        was_pressed = self._pressed
        self._pressed = False
        self._draw()
        if was_pressed and self._hovered and self._state != "disabled" and self._command is not None:
            self._command()

    def _draw(self) -> None:
        self.delete("all")
        width = max(self.winfo_width(), 2)
        height = max(self.winfo_height(), 2)
        variant = self._VARIANTS[self._variant]
        if self._state == "disabled":
            fill, text_color, border = self._DISABLED_FILL, self._DISABLED_TEXT, ""
        else:
            if self._pressed and self._hovered:
                fill = variant["pressed"]
            elif self._hovered:
                fill = variant["hover"]
            else:
                fill = variant["fill"] or self._surface
            text_color = variant["text"]
            border = variant["border"]
        image = self._image(width, height, fill, border)
        self.create_image(0, 0, anchor="nw", image=image)
        if self._align == "w":
            self.create_text(self._padx, height / 2, text=self._text, anchor="w", fill=text_color, font=self._font)
        else:
            self.create_text(width / 2, height / 2, text=self._text, anchor="center", fill=text_color, font=self._font)

    def _image(self, width: int, height: int, fill: str, border: str) -> tk.PhotoImage:
        key = (width, height, fill, border)
        image = self._images.get(key)
        if image is None:
            image = rounded_rect_image(width, height, self._radius, fill, self._surface, border or None)
            if len(self._images) >= 12:
                self._images.clear()
            self._images[key] = image
        return image


class SegmentedControl(tk.Canvas):
    """macOS 风格分段控制器，用于替代 Notebook 页签。"""

    def __init__(self, master, *, options=(), command=None, bg: str = "#FFFFFF", font=None, padx: int = 12, height: int = 34, radius: int = 9) -> None:
        super().__init__(master, highlightthickness=0, bd=0, bg=bg, cursor="hand2")
        self._font = tkfont.Font(font=font or (FONT_FAMILY, 10))
        self._font_bold = tkfont.Font(font=font or (FONT_FAMILY, 10))
        self._font_bold.configure(weight="bold")
        self._labels: list[str] = []
        self._command = command
        self._padx = padx
        self._radius = radius
        self._height = height
        self._surface = bg
        self._images: dict[tuple, tk.PhotoImage] = {}
        self.index = -1
        self.bind("<Configure>", lambda _event: self._draw())
        self.bind("<Button-1>", self._on_click)
        self.set_options(list(options))
        super().configure(height=self._height)

    def set_options(self, options: list[str]) -> None:
        self._labels = list(options)
        width = sum(self._segment_width(option) for option in self._labels) + 4
        super().configure(width=max(width, 44))
        if self._labels and self.index < 0:
            self.index = 0
        if self.index >= len(self._labels):
            self.index = len(self._labels) - 1
        self._draw()

    def select(self, index: int, notify: bool = False) -> None:
        if index == self.index:
            return
        self.index = index
        self._draw()
        if notify and self._command is not None:
            self._command(index)

    def _segment_width(self, label: str) -> int:
        return self._font_bold.measure(label) + self._padx * 2

    def _bounds(self) -> list[tuple[int, int]]:
        bounds = []
        x = 2
        for label in self._labels:
            width = self._segment_width(label)
            bounds.append((x, x + width))
            x += width
        return bounds

    def _draw(self) -> None:
        self.delete("all")
        width = max(self.winfo_width(), 4)
        height = max(self.winfo_height(), 2)
        track = self._image(width, height, self._radius, "#E8E8ED", None)
        self.create_image(0, 0, anchor="nw", image=track)
        if not self._labels:
            return
        bounds = self._bounds()
        if 0 <= self.index < len(bounds):
            x1, x2 = bounds[self.index]
            pill_width = x2 - x1 - 2
            pill_height = height - 4
            if pill_width > 4 and pill_height > 4:
                pill = self._image(pill_width, pill_height, max(self._radius - 3, 2), "#FFFFFF", "#DCDCE1")
                self.create_image(x1 + 1, 2, anchor="nw", image=pill)
        for position, label in enumerate(self._labels):
            x1, x2 = bounds[position]
            font = self._font_bold if position == self.index else self._font
            color = "#1D1D1F" if position == self.index else "#48484A"
            self.create_text((x1 + x2) / 2, height / 2, text=label, font=font, fill=color)

    def _image(self, width: int, height: int, radius: int, fill: str, border: str | None) -> tk.PhotoImage:
        key = (width, height, radius, fill, border)
        image = self._images.get(key)
        if image is None:
            image = rounded_rect_image(width, height, radius, fill, self._surface, border)
            if len(self._images) >= 12:
                self._images.clear()
            self._images[key] = image
        return image

    def _on_click(self, event) -> None:
        if not self._labels:
            return
        for position, (x1, x2) in enumerate(self._bounds()):
            if x1 <= event.x <= x2:
                self.select(position, notify=True)
                return


class TabHost(ttk.Frame):
    """带分段控制器的页签容器，接口与 Notebook.add 保持兼容。"""

    def __init__(self, master, *, surface: str = "#FFFFFF") -> None:
        super().__init__(master)
        self.selector = SegmentedControl(self, command=self._on_select, bg=surface)
        self.selector.pack(anchor="w", pady=(0, 14))
        self.frames: list[tk.Widget] = []
        self.titles: list[str] = []
        self.index = -1

    def add(self, frame, text: str | None = None) -> None:
        self.frames.append(frame)
        self.titles.append(text or f"页签 {len(self.frames)}")
        self.selector.set_options(self.titles)
        if self.index < 0:
            self._show(0)
        else:
            self._show(self.index)

    def _on_select(self, index: int) -> None:
        self._show(index)

    def _show(self, index: int) -> None:
        for frame in self.frames:
            frame.pack_forget()
        self.index = index
        self.frames[index].pack(fill="both", expand=True)
        self.selector.select(index)


class RoundedPanel(ttk.Frame):
    """圆角卡片容器：底层画布绘制圆角背景，内容放入内部 .inner 框架。"""

    def __init__(self, master, *, radius: int = 12, fill: str = "#FFFFFF", border: str | None = "#E5E5EA", surface: str = "#F5F5F7", padding=12, inset: int = 4) -> None:
        super().__init__(master)
        self._radius = radius
        self._fill = fill
        self._border = border
        self._surface = surface
        self._inset = inset
        self._image: tk.PhotoImage | None = None
        self._size = (0, 0)
        self._background = tk.Canvas(self, highlightthickness=0, bd=0, bg=surface)
        self._background.place(x=0, y=0, relwidth=1, relheight=1)
        self.inner = ttk.Frame(self, padding=padding)
        self.inner.pack(fill="both", expand=True, padx=inset, pady=inset)
        self.bind("<Configure>", self._on_configure)

    def _on_configure(self, event) -> None:
        width, height = event.width, event.height
        if width < 10 or height < 10 or (width, height) == self._size:
            return
        self._size = (width, height)
        self._image = rounded_rect_image(width, height, self._radius, self._fill, self._surface, self._border)
        self._background.delete("panel")
        self._background.create_image(0, 0, anchor="nw", image=self._image, tags="panel")


class MultiSelectDropdown(ttk.Frame):
    """Compact multi-select control that opens a list below the button."""

    def __init__(self, master) -> None:
        super().__init__(master)
        self.options: list[tuple[str, str]] = []
        self.selected: set[str] = set()
        self.popup: tk.Toplevel | None = None
        self.button = RoundedButton(self, text="请先扫描文件", variant="picker", align="w", padx=12, pady=8, command=self._open)
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

        header = ttk.Frame(popup, style="Popup.TFrame", padding=(14, 12))
        header.pack(fill="x")
        ttk.Label(header, text="选择一个或多个文件类型", style="PopupTitle.TLabel").pack(anchor="w")

        list_frame = ttk.Frame(popup, style="Popup.TFrame", padding=(12, 0))
        list_frame.pack(fill="both", expand=True)
        listbox = tk.Listbox(
            list_frame,
            selectmode=tk.MULTIPLE,
            exportselection=False,
            activestyle="none",
            borderwidth=0,
            highlightthickness=1,
            highlightbackground="#E5E5EA",
            highlightcolor="#0071E3",
            selectbackground="#0071E3",
            selectforeground="#FFFFFF",
            font=(FONT_FAMILY, 10),
        )
        scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=listbox.yview)
        listbox.configure(yscrollcommand=scrollbar.set)
        listbox.pack(side="left", fill="both", expand=True, ipady=2)
        scrollbar.pack(side="right", fill="y")
        for index, (label, value) in enumerate(self.options):
            listbox.insert("end", label)
            if value in self.selected:
                listbox.selection_set(index)

        quick = ttk.Frame(popup, style="Popup.TFrame", padding=(12, 10))
        quick.pack(fill="x", before=list_frame)
        actions = ttk.Frame(quick, style="Popup.TFrame")
        actions.pack(fill="x")
        RoundedButton(actions, text="全选", variant="link", padx=10, pady=5, command=lambda: listbox.selection_set(0, "end")).pack(side="left")
        RoundedButton(actions, text="反选", variant="link", padx=10, pady=5, command=lambda: self._invert_selection(listbox)).pack(side="left", padx=2)
        RoundedButton(actions, text="清空", variant="link", padx=10, pady=5, command=lambda: listbox.selection_clear(0, "end")).pack(side="left")

        group_map = self._available_groups()
        group_var = tk.StringVar(value=next(iter(group_map), ""))
        groups = ttk.Frame(quick, style="Popup.TFrame")
        groups.pack(fill="x", pady=(10, 0))
        ttk.Label(groups, text="按类别：", style="PopupTitle.TLabel").pack(side="left")
        ttk.Combobox(groups, textvariable=group_var, state="readonly", values=tuple(group_map)).pack(side="left", fill="x", expand=True)
        RoundedButton(groups, text="选择类别", variant="primary", padx=12, pady=6, command=lambda: self._select_group(listbox, group_map.get(group_var.get(), ()))).pack(side="left", padx=(8, 0))

        footer = ttk.Frame(popup, style="Popup.TFrame", padding=12)
        footer.pack(fill="x")
        RoundedButton(footer, text="确定", variant="primary", padx=20, pady=7, command=lambda: self._apply(listbox)).pack(side="right")
        RoundedButton(footer, text="取消", variant="secondary", padx=16, pady=7, command=self._close_popup).pack(side="right", padx=(0, 8))
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
