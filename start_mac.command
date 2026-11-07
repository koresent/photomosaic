#!/usr/bin/env bash
cd "$(dirname "$0")"

echo "============================================================"
echo "  Photomosaic Studio Launcher (macOS)"
echo "============================================================"
echo ""

if ! command -v python3 &> /dev/null; then
    echo "[ERROR] Python 3 was not found on your Mac."
    echo "Please download and install Python from: https://www.python.org/downloads/"
    echo "Or install via Homebrew: brew install python"
    read -p "Press Enter to exit..."
    exit 1
fi

if ! python3 -c "import PIL, numpy, tqdm" &> /dev/null; then
    echo "Setting up environment (Pillow, NumPy, tqdm)... This may take a minute on first run."
    if [ ! -d ".venv" ]; then
        python3 -m venv .venv
    fi
    source .venv/bin/activate
    pip install --quiet pillow numpy tqdm
else
    if [ -d ".venv" ]; then
        source .venv/bin/activate
    fi
fi

echo "Starting Photomosaic Studio..."
python3 app.py
