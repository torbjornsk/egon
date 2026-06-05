"""
Egon Trading Dashboard
Entry point for the GUI.
"""

import logging
import tkinter as tk

# Resolve log file path for packaged execution
from src.core.paths import resolve_path

log_path = str(resolve_path('trading_bot.log'))

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_path),
        logging.StreamHandler(),
    ],
)

from src.gui.app import EgonGUI


def main():
    root = tk.Tk()
    app = EgonGUI(root)
    root.protocol("WM_DELETE_WINDOW", app.on_closing)
    root.mainloop()


if __name__ == "__main__":
    main()
