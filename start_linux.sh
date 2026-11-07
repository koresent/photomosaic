#!/usr/bin/env bash
cd "$(dirname "$0")"

echo "============================================================"
echo "  Photomosaic Studio Launcher (Linux)"
echo "============================================================"
echo ""

if command -v uv &> /dev/null; then
    uv run python app.py
    exit 0
fi

if ! command -v python3 &> /dev/null; then
    echo "[ERROR] Python 3 was not found on your system."
    echo "Please install Python 3 using your package manager:"
    echo "  Ubuntu/Debian: sudo apt update && sudo apt install python3 python3-pip python3-venv"
    echo "  Fedora:        sudo dnf install python3 python3-pip"
    echo "  Arch Linux:    sudo pacman -S python python-pip"
    echo "Or download Python from https://www.python.org/downloads/"
    exit 1
fi

if ! python3 -c "import PIL, numpy, tqdm" &> /dev/null; then
    echo "Setting up environment (Pillow, NumPy, tqdm)..."
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

python3 app.py
