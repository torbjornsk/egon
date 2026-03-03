"""
Egon Trading Dashboard
Entry point for the GUI.
"""

import logging
import tkinter as tk

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('trading_bot.log'),
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
