"""Dark mode theme constants and style setup for Egon GUI."""

from tkinter import ttk

# Colors
BG_DARK = '#1e1e1e'
BG_MEDIUM = '#2d2d2d'
BG_LIGHT = '#3e3e3e'
FG = '#e0e0e0'
ACCENT = '#007acc'
SUCCESS = '#4ec9b0'
ERROR = '#f48771'
WARNING = '#dcdcaa'
NEUTRAL = '#808080'


def setup_styles():
    """Configure ttk styles for dark mode."""
    style = ttk.Style()
    style.theme_use('clam')

    style.configure('TFrame', background=BG_DARK)
    style.configure('TLabelframe', background=BG_DARK, foreground=FG, bordercolor=BG_LIGHT)
    style.configure('TLabelframe.Label', background=BG_DARK, foreground=ACCENT, font=('Arial', 9, 'bold'))
    style.configure('TLabel', background=BG_DARK, foreground=FG)
    style.configure('TButton', background=BG_MEDIUM, foreground=FG, bordercolor=BG_LIGHT)
    style.map('TButton', background=[('active', ACCENT)])

    style.configure('Treeview',
                    background=BG_MEDIUM, foreground=FG,
                    fieldbackground=BG_MEDIUM, borderwidth=0)
    style.configure('Treeview.Heading',
                    background=BG_LIGHT, foreground=FG, borderwidth=1)
    style.map('Treeview', background=[('selected', ACCENT)])
    style.map('Treeview.Heading', background=[('active', ACCENT)])
