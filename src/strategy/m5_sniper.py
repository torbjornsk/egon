"""
M5 Sniper Strategy -- LEGACY COMPATIBILITY WRAPPER.

This module re-exports the unified SniperStrategy as M5SniperStrategy
for backward compatibility with existing code that imports from here.

New code should use: from src.strategy.sniper import SniperStrategy, SniperOrder
"""

from src.strategy.sniper import SniperStrategy as M5SniperStrategy, SniperOrder

__all__ = ['M5SniperStrategy', 'SniperOrder']
