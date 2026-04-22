# -*- mode: python ; coding: utf-8 -*-
import os

# Qt Multimedia backend plugins — required for QMediaPlayer (MP3 playback).
# PyInstaller doesn't auto-collect these, so we bundle them explicitly.
QT_PLUGIN_BASE = r"C:\Python310\lib\site-packages\PyQt6\Qt6\plugins"

multimedia_dlls = [
    (os.path.join(QT_PLUGIN_BASE, "multimedia", "ffmpegmediaplugin.dll"),
     "PyQt6/Qt6/plugins/multimedia"),
    (os.path.join(QT_PLUGIN_BASE, "multimedia", "windowsmediaplugin.dll"),
     "PyQt6/Qt6/plugins/multimedia"),
]

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=multimedia_dlls,
    datas=[('assets_processed', 'assets_processed'), ('config.example.json', '.')],
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

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='TotoAgent',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['icon.ico'],
)
