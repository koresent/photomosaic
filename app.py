#!/usr/bin/env python3
"""
Photomosaic Studio Launcher
One-click entry point to start the cross-platform Photomosaic Studio GUI.
"""
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT_DIR / "generator"))

from server import start_studio_server

if __name__ == "__main__":
    start_studio_server(port=8080, open_browser=True)
