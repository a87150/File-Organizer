# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 打包配置：onedir 文件夹版、无控制台窗口、剔除无关标准库。"""

a = Analysis(
    ["run.py"],
    pathex=[],
    binaries=[],
    datas=[("file_organizer/assets/app.ico", "file_organizer/assets")],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "distutils",
        "setuptools",
        "pip",
        "pkg_resources",
        "unittest",
        "doctest",
        "pydoc",
        "pydoc_data",
        "lib2to3",
        "test",
        "idlelib",
        "turtle",
        "turtledemo",
        "tkinter.test",
        "tkinter.tix",
        "sqlite3",
        "xml",
        "xmlrpc",
        "http",
        "email",
        "html",
        "multiprocessing",
        "asyncio",
        # 哈希阶段使用 concurrent.futures.ThreadPoolExecutor，不能排除 concurrent。
        # 以下模块只被 pathlib 的 URI 功能间接引用，程序本身不用网络/SSL；
        # hashlib 会退回内置的 _sha256 实现，可省掉约 7 MB 的 OpenSSL。
        "ssl",
        "_ssl",
        "_hashlib",
        "urllib.request",
        "ftplib",
    ],
    noarchive=False,
    optimize=2,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="FileOrganizer",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    icon=["file_organizer/assets/app.ico"],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="FileOrganizer",
)
