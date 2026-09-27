# -*- mode: python ; coding: utf-8 -*-
import os
from PyInstaller.utils.hooks import collect_all

BASE_DIR = SPECPATH
BESOTA_PATH = os.path.join(BASE_DIR, 'besota')

datas = [
    ('openqore/gui/assets', 'openqore/gui/assets'),
    ('openqore/modules_json', 'openqore/modules_json'),
    ('openqore/modules_py', 'openqore/modules_py'),
    ('besota/web', 'besota/web'),
    ('besota/icon.ico', 'besota'),
    ('besota/besota_core.py', 'besota'),
    ('besota/besota_gui.py', 'besota'),
]

binaries = []
hiddenimports = [
    'besota_core',
    'besota_gui',
    'openqore.core.thumb2',
    'openqore.core.downloader',
    'openqore.core.archives',
    'openqore.core.paths',
    'openqore.core.module_base',
    'openqore.core.ui',
]

pw_datas, pw_binaries, pw_hiddenimports = collect_all('pywebview')
datas += pw_datas
binaries += pw_binaries
hiddenimports += pw_hiddenimports

a = Analysis(
    ['main.py'],
    pathex=[BASE_DIR, BESOTA_PATH],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', 'matplotlib', 'numpy'],
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
    name='openqore',
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
    icon='openqore/gui/assets/icon.ico',
)