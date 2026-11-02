"""Launcher with no working-directory dependency.

The Windows Run key and the macOS LaunchAgent both start the process from an
arbitrary directory, so this file puts its own folder (``backend``) on
``sys.path`` before importing the application package.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.cli import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
