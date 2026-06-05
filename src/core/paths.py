"""
Path resolution for packaged and source execution.

When running from source: paths resolve relative to the project root.
When running as PyInstaller exe: paths resolve relative to the exe directory.

Config and data files live NEXT TO the exe (not inside the bundle) so users
can edit config JSON files without rebuilding.
"""

import sys
from pathlib import Path


def get_app_root() -> Path:
    """Get the application root directory.

    - Source execution: the project root (where run_gui.py lives)
    - PyInstaller exe: the directory containing Egon.exe
    """
    if getattr(sys, 'frozen', False):
        # Running as compiled exe
        return Path(sys.executable).parent
    else:
        # Running from source -- project root is parent of src/
        return Path(__file__).parent.parent.parent


def resolve_path(relative_path: str) -> Path:
    """Resolve a relative path (e.g. 'config/m5_params.json') to an absolute path.

    In packaged mode, checks both:
    1. Next to the exe (user-editable copies)
    2. Inside _internal/ (bundled defaults)
    Falls back to the first path if neither exists (for file creation).
    """
    root = get_app_root()
    # Primary: next to the exe (or project root in source mode)
    primary = root / relative_path
    if primary.exists():
        return primary

    # Secondary: inside PyInstaller's _internal bundle
    if getattr(sys, 'frozen', False):
        internal = Path(sys._MEIPASS) / relative_path
        if internal.exists():
            return internal

    # Default to primary (for new file creation)
    return primary
