# -*- mode: python ; coding: utf-8 -*-

import os
import sys

from PyInstaller.utils.hooks import collect_data_files, copy_metadata

# rapidocr_onnxruntime 的 config.yaml 和 models/*.onnx 必须随包，
# 否则运行时报 "No such file or directory: .../rapidocr_onnxruntime/config.yaml"
_rapidocr_datas = collect_data_files('rapidocr_onnxruntime')
_mcp_datas = copy_metadata('mcp')
_anthropic_datas = copy_metadata('anthropic')
_mcp_hiddenimports = [
    'mcp.types',
    'mcp.client.session',
    'mcp.client.stdio',
    'mcp.client.streamable_http',
]
_openssl_binaries = []
if os.name == 'nt':
    for _dll_name in ('libssl-3-x64.dll', 'libcrypto-3-x64.dll'):
        _dll_path = os.path.join(sys.prefix, 'Library', 'bin', _dll_name)
        if os.path.isfile(_dll_path):
            _openssl_binaries.append((_dll_path, '.'))

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=_openssl_binaries,
    datas=[('app/static', 'app/static'), ('icon.ico', '.')] + _rapidocr_datas + _mcp_datas + _anthropic_datas,
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
        'app.mcp_client',
        'app.model_protocol',
        'anthropic',
        'anthropic._client',
        'anthropic.resources.messages',
        'anthropic.types',
    ] + _mcp_hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

# onedir 打包（exclude_binaries=True + COLLECT）：依赖放 _internal/ 文件夹，
# exe 直接用旁边依赖，不再每次解压 _MEI —— 根治 onefile 自更新后 Failed to load Python DLL。
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
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['icon.ico'],
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='QuickModel',
)
