# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import collect_submodules


hidden_imports = []
for package_name in (
    "app",
    "dashscope",
    "langchain",
    "langchain_openai",
    "langgraph",
    "markitdown",
):
    hidden_imports.extend(collect_submodules(package_name))


analysis = Analysis(
    ["app/desktop_runtime.py"],
    pathex=["."],
    binaries=[],
    datas=[
        ("alembic.ini", "."),
        ("migrations", "migrations"),
    ],
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["pytest"],
    noarchive=False,
    optimize=0,
)
python_archive = PYZ(analysis.pure)

executable = EXE(
    python_archive,
    analysis.scripts,
    [],
    exclude_binaries=True,
    name="OneTreeRuntime",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

collection = COLLECT(
    executable,
    analysis.binaries,
    analysis.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="OneTreeRuntime",
)
