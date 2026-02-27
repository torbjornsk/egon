"""
Market data integrations for trading bots
"""

from .alpha_vantage import AlphaVantageSentiment, ManualSentiment

__all__ = ['AlphaVantageSentiment', 'ManualSentiment']
