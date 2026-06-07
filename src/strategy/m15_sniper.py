"""
M15 Sniper Strategy -- LEGACY COMPATIBILITY WRAPPER.

This module re-exports the unified SniperStrategy as M15SniperStrategy
for backward compatibility. The M15-specific behavior (offset, timeframe)
is now driven entirely by config fields.

New code should use: from src.strategy.sniper import SniperStrategy, SniperOrder
"""

from src.strategy.sniper import SniperStrategy as M15SniperStrategy, SniperOrder

__all__ = ['M15SniperStrategy', 'SniperOrder']
