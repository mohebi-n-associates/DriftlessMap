# -*- mode: python ; coding: utf-8 -*-
"""Native macOS/Windows desktop bundle definition."""

import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules


ROOT = Path(SPECPATH).parent
PACKAGE = ROOT / "driftlessmap"
IS_MACOS = sys.platform == "darwin"
version_namespace = {}
exec((PACKAGE / "version.py").read_text(encoding="utf-8"), version_namespace)
VERSION = version_namespace["__version__"]
ICON = PACKAGE / "icons" / "app" / (
    "driftlessmap.icns" if IS_MACOS else "driftlessmap.ico"
)

datas = collect_data_files("driftlessmap")
hiddenimports = collect_submodules("pyqtgraph.opengl")

a = Analysis(
    [str(ROOT / "packaging" / "launcher.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["pytest", "ruff"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="DriftlessMap",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    icon=str(ICON),
)

bundle = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="DriftlessMap",
)

if IS_MACOS:
    app = BUNDLE(
        bundle,
        name="DriftlessMap.app",
        icon=str(ICON),
        bundle_identifier="org.mohebi-associates.driftlessmap",
        info_plist={
            "CFBundleDisplayName": "DriftlessMap",
            "CFBundleName": "DriftlessMap",
            "CFBundleShortVersionString": VERSION,
            "CFBundleVersion": VERSION,
            "NSHighResolutionCapable": True,
        },
    )
