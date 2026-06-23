# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for macOS .app bundle."""

import os
import sys

block_cipher = None

# Collect data files (skip missing directories)
datas = [('app/static', 'app/static')]
if os.path.isdir('app/skills'):
    datas.append(('app/skills', 'app/skills'))

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=[
        'app.agent',
        'app.tools',
        'app.advanced_tools',
        'app.skills',
        'app.team',
        'app.sync',
        'app.webview_app',
        'app.config',
        'app.conversation',
        'app.vision',
    ],
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
    name='QuickModel',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='QuickModel',
)

# Icon: use icon.icns if it exists, otherwise None
_icon = 'icon.icns' if os.path.exists('icon.icns') else None

# Version: read from CI tag (GITHUB_REF_NAME, e.g. "v1.5.1") when present,
# strip leading "v"; fall back to a default for local builds.
_version = os.environ.get('GITHUB_REF_NAME', '').lstrip('v') or '1.5.0'

app = BUNDLE(
    coll,
    name='QuickModel.app',
    icon=_icon,
    bundle_identifier='com.quickmodel.app',
    info_plist={
        'CFBundleName': 'QuickModel',
        'CFBundleDisplayName': 'QuickModel',
        'CFBundleVersion': _version,
        'CFBundleShortVersionString': _version,
        'NSHighResolutionCapable': True,
        'LSMinimumSystemVersion': '10.15',
    },
)
