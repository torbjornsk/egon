import logging

class RiskManager:
    def __init__(self, config):
        self.risk_per_trade = config['risk_per_trade']
        self.max_leverage = config['max_leverage']
        self.max_daily_loss = config['max_daily_loss']
        self.max_open_positions = config['max_open_positions']
        self.daily_start_balance = None
        
    def calculate_position_size(self, account_balance, stop_loss_pips, symbol_info):
        """Calculate position size based on risk percentage"""
        risk_amount = account_balance * self.risk_per_trade
        
        # Calculate pip value
        pip_value = symbol_info.trade_tick_value * symbol_info.trade_tick_size
        
        # Position size in lots
        position_size = risk_amount / (stop_loss_pips * pip_value)
        
        # Apply leverage limit
        max_position_by_leverage = (account_balance * self.max_leverage) / symbol_info.trade_contract_size
        position_size = min(position_size, max_position_by_leverage)
        
        # Round to symbol's volume step
        position_size = round(position_size / symbol_info.volume_step) * symbol_info.volume_step
        
        # Ensure within min/max limits
        position_size = max(symbol_info.volume_min, min(position_size, symbol_info.volume_max))
        
        return position_size
    
    def check_daily_loss_limit(self, current_balance):
        """Check if daily loss limit has been reached"""
        if self.daily_start_balance is None:
            self.daily_start_balance = current_balance
            return False
        
        daily_loss = (self.daily_start_balance - current_balance) / self.daily_start_balance
        
        if daily_loss >= self.max_daily_loss:
            logging.warning(f"Daily loss limit reached: {daily_loss:.2%}")
            return True
        
        return False
    
    def can_open_position(self, open_positions_count):
        """Check if new position can be opened"""
        return open_positions_count < self.max_open_positions
    
    def reset_daily_tracking(self, current_balance):
        """Reset daily tracking (call at start of new trading day)"""
        self.daily_start_balance = current_balance
