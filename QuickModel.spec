# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import collect_data_files

# rapidocr_onnxruntime 的 config.yaml 和 models/*.onnx 必须随包，
# 否则运行时报 "No such file or directory: .../rapidocr_onnxruntime/config.yaml"
_rapidocr_datas = collect_data_files('rapidocr_onnxruntime')

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[('app/static', 'app/static'), ('icon.ico', '.')] + _rapidocr_datas,
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
