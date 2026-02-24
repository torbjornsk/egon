from abc import ABC, abstractmethod
import pandas as pd

class BaseStrategy(ABC):
    def __init__(self, params):
        self.params = params
        
    @abstractmethod
    def generate_signals(self, data):
        """Generate trading signals from data
        Returns: DataFrame with 'signal' column (1=buy, -1=sell, 0=hold)
        """
        pass
    
    @abstractmethod
    def calculate_indicators(self, data):
        """Calculate technical indicators"""
        pass
    
    def validate_signal(self, signal, account_info, open_positions):
        """Validate if signal should be executed based on risk management"""
        return True
