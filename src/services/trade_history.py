"""
Trade history service  --  exit reason loading for GUI display.

Auto-discovers all exit_reasons_*.json files in the data/ directory
so new bot types are included without code changes.
"""

import glob
import json
import os
from src.core.paths import resolve_path


def load_exit_reasons() -> dict:
    """Load exit reasons from all bot JSON files in data/ directory."""
    reasons = {}
    data_dir = str(resolve_path('data'))
    pattern = os.path.join(data_dir, 'exit_reasons_*.json')

    for path in glob.glob(pattern):
        try:
            with open(path, 'r') as f:
                reasons.update(json.load(f))
        except Exception:
            pass

    return reasons
