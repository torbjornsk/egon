"""
M1 Sniper Strategy -- LEGACY COMPATIBILITY WRAPPER.

This module re-exports the unified SniperStrategy as M1SniperStrategy
for backward compatibility. The M1-specific behavior (offset, timeframe)
is now driven entirely by config fields.

New code should use: from src.strategy.sniper import SniperStrategy, SniperOrder
"""

from src.strategy.sniper import SniperStrategy as M1SniperStrategy, SniperOrder

__all__ = ['M1SniperStrategy', 'SniperOrder']
