# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import collect_submodules, collect_data_files

block_cipher = None

APP_NAME = "BCX Comic Lister"
ICON_PATH = "resources/bcx.icns"   # generate from your bcx.png

hiddenimports = []
hiddenimports += collect_submodules("PyQt5.QtWebEngineWidgets")
hiddenimports += collect_submodules("PyQt5.QtWebEngineCore")

datas = []
datas += [("resources", "resources")]
datas += [("tools", "tools")]
datas += collect_data_files("PyQt5.QtWebEngineWidgets", include_py_files=False)
datas += collect_data_files("PyQt5.QtWebEngineCore", include_py_files=False)

a = Analysis(
    ["app.py"],
    pathex=["."],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=APP_NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name=APP_NAME,
)

app = BUNDLE(
    coll,
    name=f"{APP_NAME}.app",
    icon=ICON_PATH,
    bundle_identifier="com.bcx.comiclister",
)