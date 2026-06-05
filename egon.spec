# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec file for Egon Trading Bot.

Builds a single-folder distribution including:
- The GUI application (Egon.exe)
- All config JSON files
- Data directory for exit reasons
- MetaTrader5 DLLs (auto-detected)
"""

import os
import sys
from pathlib import Path

block_cipher = None

# Find MetaTrader5 package location for DLL inclusion
import importlib.util
mt5_spec = importlib.util.find_spec('MetaTrader5')
mt5_path = Path(mt5_spec.origin).parent if mt5_spec else None

# Collect MT5 DLLs
mt5_binaries = []
if mt5_path:
    for dll in mt5_path.glob('*.dll'):
        mt5_binaries.append((str(dll), 'MetaTrader5'))
    for pyd in mt5_path.glob('*.pyd'):
        mt5_binaries.append((str(pyd), 'MetaTrader5'))

a = Analysis(
    ['run_gui.py'],
    pathex=['.'],
    binaries=mt5_binaries,
    datas=[
        ('config', 'config'),
        ('data', 'data'),
    ],
    hiddenimports=[
        'MetaTrader5',
        'pandas',
        'numpy',
        'pytz',
        'matplotlib',
        'matplotlib.backends.backend_tkagg',
        'tkinter',
        'src',
        'src.bot',
        'src.bot.base',
        'src.bot.m1_bot',
        'src.bot.m5_bot',
        'src.bot.m15_bot',
        'src.bot.sniper_bot',
        'src.bot.zone_bot',
        'src.bot.tick_scalper',
        'src.bot.momentum_scalper',
        'src.core',
        'src.core.broker',
        'src.core.config',
        'src.core.indicators',
        'src.core.liquidity',
        'src.core.mt5_broker',
        'src.core.mt5_client',
        'src.core.position',
        'src.core.risk',
        'src.core.rsi_levels',
        'src.core.tick_analysis',
        'src.core.timezone',
        'src.core.trend',
        'src.gui',
        'src.gui.app',
        'src.gui.theme',
        'src.services',
        'src.services.bot_manager',
        'src.services.market_data',
        'src.services.trade_history',
        'src.strategy',
        'src.strategy.base',
        'src.strategy.liquidity_zones',
        'src.strategy.m15_scalping',
        'src.strategy.m15_sniper',
        'src.strategy.m1_scalping',
        'src.strategy.m1_sniper',
        'src.strategy.m5_scalping',
        'src.strategy.m5_sniper',
        'src.strategy.momentum_signal',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'pytest',
        'ruff',
        'mypy',
        'black',
        'IPython',
        'notebook',
        'sphinx',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='Egon',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,  # No console window (GUI app)
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='Egon',
)
