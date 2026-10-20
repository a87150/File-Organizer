"""正则表达式帮助窗口：基础教学 + 常用模板。

窗口顶部的页面切换按钮固定在顶部（不随内容滚动），只有下方内容区滚动。
"""

from __future__ import annotations

import tkinter as tk

import customtkinter as ctk

from .theme import ACCENT, APP_BG, BORDER, CARD_BG, SCROLL_THUMB, SCROLL_THUMB_ACTIVE, TEXT_PRIMARY, TEXT_SECONDARY
from .theme import apply_window_frame
from .theme import font as ui_font
from .widgets import RoundedButton, SegmentedControl, hint, label, section

# --------------------------------------------------------------------------- 文案

TUTORIAL_SECTIONS: tuple[tuple[str, tuple[tuple[str, str], ...]], ...] = (
    (
        "它是什么",
        (
            ("作用", "正则表达式用一小段符号描述“什么样的文本”，用来查找、替换或截取文件名。"),
            ("用在哪里", "重命名页勾选「查找内容使用正则表达式」后，「查找」里填的就是正则；分类整理页的「文件名提取规则」也用它。"),
            ("语法标准", "本工具使用 Python 的 re 语法，支持分组、命名分组等常见写法。"),
        ),
    ),
    (
        "常用元字符",
        (
            (".", "任意一个字符（换行除外）"),
            ("^", "文本开头，即整个文件名的开头"),
            ("$", "文本结尾，常用来限定扩展名，如 \\.mp4$"),
            ("\\d", "一个数字，等价于 [0-9]"),
            ("\\w", "字母、数字或下划线（Python 3 中也包含中文）"),
            ("\\s", "空白字符（空格、制表符）"),
            ("[abc]", "方括号里的任意一个字符"),
            ("[^abc]", "除方括号里字符以外的任意一个字符"),
            ("[一-龥]", "任意一个常用汉字"),
            ("|", "或，例如 mp4|mkv 表示 mp4 或 mkv"),
            ("()", "分组；替换里可用 \\1、\\2 引用，提取时表示“只要括号里的部分”"),
        ),
    ),
    (
        "量词（重复次数）",
        (
            ("*", "前面的内容出现 0 次或多次"),
            ("+", "前面的内容出现 1 次或多次"),
            ("?", "前面的内容出现 0 次或 1 次；也用于非贪婪写法如 .*?"),
            ("{3}", "正好 3 次"),
            ("{2,5}", "2 到 5 次"),
            ("{2,}", "至少 2 次"),
        ),
    ),
    (
        "实用写法",
        (
            ("转义", "想匹配 . + ( ) 等符号本身，要在前面加反斜杠，例如 \\. 表示真正的点。"),
            ("大小写", "默认区分大小写，可写 [Mm][Pp]4 兼顾两种写法；也可在开头加 (?i) 忽略大小写。"),
            ("去掉扩展名再匹配", "规则匹配的是完整文件名，结尾可用 \\.mp4$ 之类限定。"),
            ("贪婪与非贪婪", ".* 会尽可能多匹配，.*? 会尽可能少匹配，提取中间内容时常用后者。"),
        ),
    ),
)

TEMPLATES: tuple[tuple[str, str, str], ...] = (
    ("提取下划线前的项目名", r"^([^_]+)_", "项目A_合同.pdf → 项目A"),
    ("提取括号里的内容", r"\(([^()]*)\)", "报告(最终版).docx → 最终版"),
    ("提取日期 2026-10-19", r"(\d{4})-(\d{2})-(\d{2})", "捕获组 1/2/3 分别是年、月、日"),
    ("提取末尾数字序号", r"(\d+)$", "封面 03.jpg → 03"),
    ("匹配“副本 / copy / 复制”", r"(?i)(副本|copy|复制)", "忽略大小写地找这三种写法"),
    ("连续空格压成一个", r"\s{2,}", "配合“替换为”填一个空格使用"),
    ("只匹配常见视频扩展名", r"\.(mp4|mkv|avi|mov|flv)$", "重命名页的查找框里可直接用"),
    ("去掉版本号", r"[-_ ]?v\d+(\.\d+)*", "方案_v2.1.pdf → 方案.pdf"),
    ("提取花括号里的编号", r"\{([^{}]+)\}", "片段{001}.mp3 → 001"),
    ("匹配纯数字文件名", r"^\d+$", "20261019.jpg 这类纯数字命名"),
    ("清理文件名里的非法字符", r"[\\/:*?\"<>|]", "替换为空即可去掉 Windows 不允许的字符"),
)


# --------------------------------------------------------------------------- 窗口


class RegexHelpWindow(ctk.CTkToplevel):
    """正则帮助：两个页面用顶部按钮切换，按钮固定不滚动。"""

    def __init__(self, master) -> None:
        super().__init__(master)
        self.title("正则表达式帮助")
        self.geometry("800x660")
        self.minsize(680, 520)
        self.configure(fg_color=APP_BG)
        self.transient(master)
        self._tabs = ["基础教学", "常用模板"]
        self._pages: list[ctk.CTkFrame] = []
        self._template_fields: list[ctk.CTkEntry] = []

        wrapper = ctk.CTkFrame(self, corner_radius=0, fg_color=APP_BG)
        wrapper.pack(fill="both", expand=True, padx=18, pady=16)

        header = ctk.CTkFrame(wrapper, corner_radius=0, fg_color="transparent")
        header.pack(fill="x")
        label(header, "正则表达式", size=15, weight="bold").pack(side="left")
        hint(header, "顶部按钮切换页面，正文可滚动", wraplength=320).pack(side="left", padx=(10, 0))

        # 固定区：页面切换按钮，不参与滚动。
        switcher = ctk.CTkFrame(wrapper, corner_radius=0, fg_color="transparent")
        switcher.pack(fill="x", pady=(12, 10))
        self.selector = SegmentedControl(switcher, options=self._tabs, command=self._show_page, bg=APP_BG)
        self.selector.pack(side="left")

        # 滚动区：只有正文滚动。
        self.body = ctk.CTkScrollableFrame(
            wrapper,
            corner_radius=12,
            fg_color=CARD_BG,
            border_width=1,
            border_color=BORDER,
            scrollbar_button_color=SCROLL_THUMB,
            scrollbar_button_hover_color=SCROLL_THUMB_ACTIVE,
        )
        self.body.pack(fill="both", expand=True)

        self._build_tutorial(self._new_page())
        self._build_templates(self._new_page())
        self._show_page(0)

        self.bind("<Escape>", lambda _event: self.destroy())
        self.after(80, self._focus_self)
        self.after(100, lambda: apply_window_frame(self))

    def _focus_self(self) -> None:
        try:
            self.focus_force()
        except tk.TclError:
            pass

    def _new_page(self) -> ctk.CTkFrame:
        page = ctk.CTkFrame(self.body, corner_radius=0, fg_color="transparent")
        self._pages.append(page)
        return page

    def _show_page(self, index: int) -> None:
        for page in self._pages:
            page.pack_forget()
        self._pages[index].pack(fill="both", expand=True, padx=4, pady=4)
        self.selector.select(index)
        # 依赖 CTk 内部结构（_parent_canvas），升级需人工回归；缺失时只是不回到顶部。
        try:
            self.body._parent_canvas.yview_moveto(0)
        except AttributeError:
            pass

    # ------------------------------------------------------------------ 页面内容

    def _build_tutorial(self, page: ctk.CTkFrame) -> None:
        hint(page, "下面是最常用的部分，掌握后基本够用来重命名和提取文件名。", wraplength=640).pack(anchor="w", padx=2, pady=(2, 10))
        for title, rows in TUTORIAL_SECTIONS:
            card = section(page, title, pady=(0, 10))
            grid = ctk.CTkFrame(card, corner_radius=0, fg_color="transparent")
            grid.pack(fill="x")
            grid.columnconfigure(0, minsize=136)
            grid.columnconfigure(1, weight=1)
            for row, (key, text) in enumerate(rows):
                key_label = label(grid, key, color=TEXT_SECONDARY, font=ui_font(12))
                key_label.grid(row=row, column=0, sticky="nw", pady=4, padx=(0, 10))
                ctk.CTkLabel(
                    grid,
                    text=text,
                    font=ui_font(12),
                    text_color=TEXT_PRIMARY,
                    anchor="w",
                    justify="left",
                    wraplength=560,
                ).grid(row=row, column=1, sticky="w", pady=4)

    def _build_templates(self, page: ctk.CTkFrame) -> None:
        hint(page, "点「复制」把表达式放进剪贴板，粘贴到查找框或文件名提取规则里即可。", wraplength=640).pack(anchor="w", padx=2, pady=(2, 10))
        for name, pattern, description in TEMPLATES:
            card = section(page, name, pady=(0, 10))
            row = ctk.CTkFrame(card, corner_radius=0, fg_color="transparent")
            row.pack(fill="x")
            field = ctk.CTkEntry(
                row,
                font=ctk.CTkFont(family="Consolas", size=13),
                fg_color=APP_BG,
                border_color=BORDER,
                border_width=1,
                corner_radius=8,
                height=32,
                text_color=ACCENT,
            )
            field.insert(0, pattern)
            field.configure(state="readonly")
            field.pack(side="left", fill="x", expand=True)
            self._template_fields.append(field)
            copy_button = RoundedButton(
                row,
                text="复制",
                variant="secondary",
                padx=12,
                pady=6,
                height=32,
            )
            copy_button.configure(command=lambda value=pattern, button=copy_button: self._copy(value, button))
            copy_button.pack(side="left", padx=(8, 0))
            hint(card, description, wraplength=600).pack(anchor="w", pady=(6, 0))

    def _copy(self, value: str, button: ctk.CTkButton | None = None) -> None:
        self.clipboard_clear()
        self.clipboard_append(value)
        if button is None:
            return
        try:
            button.configure(text="已复制 ✓")
            self.after(800, lambda: RegexHelpWindow._restore_copy_button(button))
        except tk.TclError:
            pass

    @staticmethod
    def _restore_copy_button(button: ctk.CTkButton) -> None:
        try:
            if button.winfo_exists():
                button.configure(text="复制")
        except tk.TclError:
            pass
