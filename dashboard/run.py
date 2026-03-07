#!/usr/bin/env python3
"""Entry point: python dashboard/run.py"""

import os
import sys

# Ensure project root is importable
_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from dashboard.app import create_app

if __name__ == "__main__":
    app = create_app()
    app.run(debug=True, host="localhost", port=8060)
