#!/bin/bash
# Build QuickModel.app for macOS
set -e

cd "$(dirname "$0")"

echo "Installing build dependencies..."
pip3 install pyinstaller

echo "Building QuickModel.app..."
pyinstaller main_mac.spec --clean

echo ""
echo "Done! App bundle is at: dist/QuickModel.app"
echo "You can drag it to /Applications to install."
