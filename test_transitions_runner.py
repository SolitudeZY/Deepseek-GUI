"""
CSS Transition 最小可行性测试
加载项目 CSS 环境下的测试页面
"""
import os
import webview

base_dir = os.path.dirname(os.path.abspath(__file__))
static_dir = os.path.join(base_dir, 'app', 'static')

# 通过 pywebview HTTP 服务器加载（和主程序一样）
test_path = os.path.join(static_dir, 'test_with_project_css.html')

if __name__ == "__main__":
    window = webview.create_window(
        'Test - With Project CSS',
        test_path,
        width=800,
        height=700,
    )
    webview.start(debug=True, private_mode=False)
