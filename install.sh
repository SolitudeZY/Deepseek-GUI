#!/bin/bash
# QuickModel macOS 一键安装脚本
# 使用方法：打开终端，粘贴以下命令：
#   bash install.sh
set -e

echo "=== QuickModel macOS 安装 ==="
echo ""

# 检查 Python
if ! command -v python3 &>/dev/null; then
    echo "未检测到 Python，正在安装..."
    echo "请在弹出的对话框中点击「安装」"
    xcode-select --install 2>/dev/null || true
    echo ""
    echo "如果上面没有弹窗，请手动安装 Python："
    echo "  访问 https://www.python.org/downloads/ 下载安装"
    echo ""
    read -p "安装完 Python 后按回车继续..."
fi

echo "正在安装依赖..."
pip3 install --user -r requirements.txt

echo ""
echo "=== 安装完成！==="
echo ""
echo "运行方式：双击 run.command 或在终端执行 ./run.sh"
echo ""
