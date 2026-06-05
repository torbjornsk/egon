"""
Trade history service  --  exit reason loading for GUI display.
"""

import json
import os


def load_exit_reasons() -> dict:
    """Load exit reasons from all bot JSON files."""
    reasons = {}
    for path in ['data/exit_reasons_m1.json', 'data/exit_reasons_m5.json',
                 'data/exit_reasons_m15.json', 'data/exit_reasons_lz.json',
                 'data/exit_reasons_m5s.json', 'data/exit_reasons_m1s.json',
                 'data/exit_reasons_m15s.json', 'data/exit_reasons_tick.json',
                 'data/exit_reasons_momentum.json']:
        if os.path.exists(path):
            try:
                with open(path, 'r') as f:
                    reasons.update(json.load(f))
            except Exception:
                pass
    return reasons
