"""
CSS Transition 最小可行性测试
在与主程序相同的 pywebview + WebView2 环境中加载测试页面
"""
import os
import webview

html_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'test_transitions.html')
# 使用 file:// URL 避免 pywebview 内置 HTTP 服务器的路径问题
file_url = 'file:///' + html_path.replace('\\', '/')

if __name__ == "__main__":
    # 与 main.py 相同的配置
    window = webview.create_window(
        'CSS Transition Test',
        url=file_url,
        width=800,
        height=900,
    )
    webview.start(debug=True, private_mode=False)
