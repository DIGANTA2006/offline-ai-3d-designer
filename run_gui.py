#!/usr/bin/env python3
"""
Launcher script for the AI 3D Designer GUI.
"""

import sys
from pathlib import Path

# Add src to path
src_path = Path(__file__).parent / "src"
sys.path.insert(0, str(src_path))

from ai3d_designer.gui.app import main

if __name__ == "__main__":
    main()
