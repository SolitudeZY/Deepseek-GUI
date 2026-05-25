#!/bin/bash
# QuickModel macOS - Run from source
set -e

cd "$(dirname "$0")"

# Check Python version
python3 -c "import sys; assert sys.version_info >= (3, 10), 'Python 3.10+ required'" 2>/dev/null || {
    echo "Error: Python 3.10+ is required"
    exit 1
}

# Install dependencies if needed
if ! python3 -c "import openai, webview" 2>/dev/null; then
    echo "Installing dependencies..."
    pip3 install -r requirements.txt
fi

echo "Starting QuickModel..."
python3 main.py
