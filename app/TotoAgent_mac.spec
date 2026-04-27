# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec — macOS build (.app bundle).

Run from the app/ folder on a Mac:

    pip install -r requirements.txt pyinstaller
    pyinstaller TotoAgent_mac.spec --noconfirm

Output: dist/TotoAgent.app
Zip it for distribution:

    cd dist && zip -r TotoAgent-mac.zip TotoAgent.app
"""
import glob
import os
import sys

from PyInstaller.utils.hooks import get_package_paths

# Locate PyQt6 multimedia plugins on the build host. PyInstaller does not
# auto-collect Qt6 plugin .dylibs reliably, so we discover them dynamically
# instead of hardcoding a path (the runner has Python in a different place
# than a developer Mac would).
_, pyqt6_root = get_package_paths("PyQt6")
QT_PLUGIN_BASE = os.path.join(pyqt6_root, "Qt6", "plugins")

multimedia_plugins = []
multimedia_dir = os.path.join(QT_PLUGIN_BASE, "multimedia")
if os.path.isdir(multimedia_dir):
    for plug in glob.glob(os.path.join(multimedia_dir, "*.dylib")):
        multimedia_plugins.append((plug, "PyQt6/Qt6/plugins/multimedia"))


a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=multimedia_plugins,
    datas=[
        ('assets_processed', 'assets_processed'),
        ('config.example.json', '.'),
    ],
    hiddenimports=[
        'PyQt6.QtMultimedia',
        'PyQt6.QtMultimediaWidgets',
        'PyQt6.sip',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

# On macOS we use COLLECT + BUNDLE instead of a one-file EXE so that we can
# produce a proper .app bundle that Finder treats as a single application.
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='TotoAgent',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,                 # UPX breaks signed dylibs on macOS
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=True,       # required so dropped files reach sys.argv on macOS
    target_arch=None,          # universal2 if PyInstaller + Python support it; else host arch
    codesign_identity=None,    # set to a Developer ID for distribution
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
    name='TotoAgent',
)

app = BUNDLE(
    coll,
    name='TotoAgent.app',
    icon=None,                 # supply a .icns later for a proper Dock icon
    bundle_identifier='com.gabrielsakc.totoagent',
    info_plist={
        'NSHighResolutionCapable': True,
        'LSUIElement': False,
        'CFBundleShortVersionString': '0.2.0',
        'CFBundleVersion': '0.2.0',
        'NSHumanReadableCopyright': 'Toto agent',
        # IMAP polls Gmail; declare the network usage so macOS doesn't surprise
        # users on first connection. (Network access doesn't actually require a
        # purpose string today, but it's good hygiene.)
    },
)
