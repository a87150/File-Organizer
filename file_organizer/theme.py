from __future__ import annotations

from tkinter import ttk

FONT_FAMILY = "Microsoft YaHei UI"
BASE_FONT = (FONT_FAMILY, 10)
SUBTITLE_FONT = (FONT_FAMILY, 10)
SECTION_FONT = (FONT_FAMILY, 10, "bold")
BOLD_FONT = (FONT_FAMILY, 10, "bold")
HEADING_FONT = (FONT_FAMILY, 9)

APP_BG = "#F5F5F7"
CARD_BG = "#FFFFFF"
BORDER = "#E5E5EA"
FIELD_BORDER = "#D2D2D7"
TEXT_PRIMARY = "#1D1D1F"
TEXT_SECONDARY = "#6E6E73"
ACCENT = "#0071E3"
SEGMENT_BG = "#E8E8ED"
HOVER_BG = "#F2F2F7"
MUTED_BG = "#AEAEB2"
SCROLL_THUMB = "#C7C7CC"
SCROLL_THUMB_ACTIVE = "#AEAEB2"


def configure_styles(widget) -> None:
    """为整个应用配置 ttk 主题与自定义样式（浅色、圆润、接近 macOS 风格）。"""
    style = ttk.Style(widget)
    style.theme_use("clam")
    font = BASE_FONT
    widget.option_add("*Font", font)
    widget.option_add("*TCombobox*Listbox.background", CARD_BG)
    widget.option_add("*TCombobox*Listbox.foreground", TEXT_PRIMARY)
    widget.option_add("*TCombobox*Listbox.selectBackground", ACCENT)
    widget.option_add("*TCombobox*Listbox.selectForeground", "#FFFFFF")
    widget.option_add("*TCombobox*Listbox.font", f"{{{FONT_FAMILY}}} 10")

    style.configure("TFrame", background=CARD_BG)
    style.configure("App.TFrame", background=APP_BG)
    style.configure("Popup.TFrame", background=CARD_BG)

    style.configure("TLabel", background=CARD_BG, foreground=TEXT_PRIMARY, font=font)
    style.configure("Subtitle.TLabel", background=APP_BG, foreground=TEXT_SECONDARY, font=SUBTITLE_FONT)
    style.configure("Section.TLabel", background=CARD_BG, foreground=TEXT_PRIMARY, font=SECTION_FONT)
    style.configure("PopupTitle.TLabel", background=CARD_BG, foreground=TEXT_PRIMARY, font=BOLD_FONT)

    style.configure("TLabelframe", background=CARD_BG, bordercolor=BORDER)
    style.configure("TLabelframe.Label", background=CARD_BG, foreground=TEXT_SECONDARY, font=BOLD_FONT)

    style.configure("TPanedwindow", background=APP_BG)
    style.configure("Sash", sashthickness=8, gripsize=0, background=APP_BG)
    style.map("Sash", background=[("active", SEGMENT_BG), ("pressed", SCROLL_THUMB)])

    style.configure(
        "TCheckbutton",
        background=CARD_BG,
        foreground=TEXT_PRIMARY,
        focuscolor=CARD_BG,
        indicatorbackground=CARD_BG,
        indicatorforeground=ACCENT,
        indicatormargin=3,
    )
    style.map(
        "TCheckbutton",
        background=[("active", CARD_BG)],
        indicatorbackground=[("pressed", HOVER_BG), ("disabled", CARD_BG)],
        indicatorforeground=[("disabled", MUTED_BG)],
    )
    style.configure(
        "TRadiobutton",
        background=CARD_BG,
        foreground=TEXT_PRIMARY,
        focuscolor=CARD_BG,
        indicatorbackground=CARD_BG,
        indicatorforeground=ACCENT,
        indicatormargin=3,
    )
    style.map(
        "TRadiobutton",
        background=[("active", CARD_BG)],
        indicatorbackground=[("pressed", HOVER_BG), ("disabled", CARD_BG)],
        indicatorforeground=[("disabled", MUTED_BG)],
    )

    style.configure("TEntry", fieldbackground=CARD_BG, foreground=TEXT_PRIMARY, bordercolor=FIELD_BORDER, lightcolor=FIELD_BORDER, darkcolor=FIELD_BORDER, padding=6)
    style.configure("Modern.TEntry", fieldbackground=CARD_BG, foreground=TEXT_PRIMARY, bordercolor=FIELD_BORDER, lightcolor=FIELD_BORDER, darkcolor=FIELD_BORDER, padding=8)
    style.map("TEntry", bordercolor=[("focus", ACCENT)], lightcolor=[("focus", ACCENT)])
    style.configure("TCombobox", fieldbackground=CARD_BG, background=CARD_BG, foreground=TEXT_PRIMARY, bordercolor=FIELD_BORDER, lightcolor=FIELD_BORDER, darkcolor=FIELD_BORDER, arrowcolor=TEXT_SECONDARY, arrowsize=13, padding=5)
    style.map("TCombobox", fieldbackground=[("readonly", CARD_BG)], background=[("readonly", CARD_BG)], foreground=[("readonly", TEXT_PRIMARY)], bordercolor=[("focus", ACCENT)])
    style.configure("TSpinbox", fieldbackground=CARD_BG, foreground=TEXT_PRIMARY, bordercolor=FIELD_BORDER, lightcolor=FIELD_BORDER, darkcolor=FIELD_BORDER, arrowcolor=TEXT_SECONDARY, padding=5)
    style.map("TSpinbox", bordercolor=[("focus", ACCENT)])

    style.configure("TButton", padding=(14, 8), background=SEGMENT_BG, foreground=TEXT_PRIMARY, borderwidth=0, focuscolor=SEGMENT_BG)
    style.map("TButton", background=[("active", "#DEDEE3"), ("disabled", HOVER_BG)], foreground=[("disabled", MUTED_BG)])

    style.configure("Treeview", background=CARD_BG, fieldbackground=CARD_BG, foreground=TEXT_PRIMARY, rowheight=32, borderwidth=0, font=font)
    style.configure("Treeview.Heading", background=CARD_BG, foreground=TEXT_SECONDARY, font=HEADING_FONT, padding=(10, 9), relief="flat")
    style.map("Treeview.Heading", background=[("active", HOVER_BG)])
    style.map("Treeview", background=[("selected", "#E8F1FF")], foreground=[("selected", TEXT_PRIMARY)])

    for orient in ("Vertical", "Horizontal"):
        style.configure(
            f"{orient}.TScrollbar",
            background=SCROLL_THUMB,
            troughcolor=CARD_BG,
            bordercolor=CARD_BG,
            arrowcolor=TEXT_SECONDARY,
            lightcolor=SCROLL_THUMB,
            darkcolor=SCROLL_THUMB,
            arrowsize=12,
            gripsize=0,
        )
        style.map(f"{orient}.TScrollbar", background=[("active", SCROLL_THUMB_ACTIVE), ("pressed", SCROLL_THUMB_ACTIVE)])

    style.configure("Horizontal.TProgressbar", troughcolor=SEGMENT_BG, background=ACCENT, bordercolor=SEGMENT_BG, lightcolor=ACCENT, darkcolor=ACCENT, thickness=6)

    style.configure("Status.TFrame", background=CARD_BG)
    style.configure("Status.TLabel", background=CARD_BG, foreground=TEXT_SECONDARY, font=font)
    style.configure("StatusDot.TLabel", background=CARD_BG, foreground=ACCENT, font=font)
