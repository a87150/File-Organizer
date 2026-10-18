"""应用主题：配色、字体与 CustomTkinter 外观设置。

界面基于 CustomTkinter（自带抗锯齿圆角绘制），仅保留少量 ttk 元素
（Treeview 预览表、Panedwindow 分栏）并在这里统一配色。
"""

from __future__ import annotations

from tkinter import ttk

import customtkinter as ctk

FONT_FAMILY = "Microsoft YaHei UI"

APP_BG = "#F5F5F7"
CARD_BG = "#FFFFFF"
BORDER = "#E5E5EA"
FIELD_BORDER = "#D2D2D7"
TEXT_PRIMARY = "#1D1D1F"
TEXT_SECONDARY = "#6E6E73"
ACCENT = "#0071E3"
ACCENT_HOVER = "#0077ED"
ACCENT_PRESSED = "#0062C4"
SEGMENT_BG = "#E8E8ED"
SEGMENT_HOVER = "#DEDEE3"
HOVER_BG = "#F2F2F7"
MUTED_BG = "#AEAEB2"
SCROLL_THUMB = "#C7C7CC"
SCROLL_THUMB_ACTIVE = "#AEAEB2"
SELECT_BG = "#E8F1FF"
CHECK_BORDER = "#C7C7CC"

# 全局字号偏移：整体比默认大一档，观感更舒展。
FONT_SIZE_OFFSET = 1

_fonts: dict[tuple[int, str], ctk.CTkFont] = {}


def font(size: int = 12, weight: str = "normal") -> ctk.CTkFont:
    """按字号/字重获取缓存的 CTkFont（需要已存在 Tk 根窗口）。"""
    size = size + FONT_SIZE_OFFSET
    key = (size, weight)
    cached = _fonts.get(key)
    if cached is None:
        cached = ctk.CTkFont(family=FONT_FAMILY, size=size, weight=weight)
        _fonts[key] = cached
    return cached


def configure_styles(widget) -> None:
    """设置浅色外观，并为 ttk 的 Treeview / Panedwindow / Sash 配置苹果风配色。"""
    ctk.set_appearance_mode("light")
    ctk.set_default_color_theme("blue")
    _fonts.clear()

    style = ttk.Style(widget)
    style.theme_use("clam")

    style.configure("TPanedwindow", background=APP_BG)
    style.configure("Sash", sashthickness=8, gripsize=0, background=APP_BG)
    style.map("Sash", background=[("active", SEGMENT_BG), ("pressed", SCROLL_THUMB)])

    style.configure(
        "Treeview",
        background=CARD_BG,
        fieldbackground=CARD_BG,
        foreground=TEXT_PRIMARY,
        rowheight=32,
        borderwidth=0,
        font=(FONT_FAMILY, 11),
    )
    style.configure(
        "Treeview.Heading",
        background=CARD_BG,
        foreground=TEXT_SECONDARY,
        font=(FONT_FAMILY, 11),
        padding=(10, 9),
        relief="flat",
    )
    style.map("Treeview.Heading", background=[("active", HOVER_BG)])
    style.map("Treeview", background=[("selected", SELECT_BG)], foreground=[("selected", TEXT_PRIMARY)])
