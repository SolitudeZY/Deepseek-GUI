import sys
import os
import platform

# 确保 app 目录在路径中（PyInstaller 打包后也能找到）
if getattr(sys, 'frozen', False):
    base_dir = sys._MEIPASS
else:
    base_dir = os.path.dirname(os.path.abspath(__file__))

sys.path.insert(0, base_dir)

import webview
from app.webview_app import API, get_html_path, patch_http_root

if __name__ == "__main__":
    api = API()

    # Icon: prefer .icns on macOS, .ico on Windows, .png as fallback
    if platform.system() == "Darwin":
        icon_path = os.path.join(base_dir, 'icon.icns')
        if not os.path.exists(icon_path):
            icon_path = os.path.join(base_dir, 'icon.png')
    else:
        icon_path = os.path.join(base_dir, 'icon.ico')
        if not os.path.exists(icon_path):
            icon_path = os.path.join(base_dir, 'icon.png')

    window = webview.create_window(
        'QuickModel',
        get_html_path(),
        js_api=api,
        width=1100,
        height=700,
        min_size=(800, 500),
    )
    api.set_window(window)

    # 规避 pywebview 6.x Bottle server 对裸 `/` 请求报 500 的 bug（须在 webview.start 前）
    patch_http_root()

    # macOS: pywebview uses WebKit (cocoa); no private_mode param needed
    start_kwargs = {"debug": False}
    if os.path.exists(icon_path):
        start_kwargs["icon"] = icon_path
    if platform.system() == "Windows":
        start_kwargs["private_mode"] = False

    webview.start(**start_kwargs)
