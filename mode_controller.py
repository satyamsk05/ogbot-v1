import os
import time
import config  # type: ignore
from execution import get_client, check_balance  # type: ignore
from strategy_5m import Strategy5M  # type: ignore
from strategy_15m import Strategy15M  # type: ignore

# COLORS
RED    = "\033[91m"
GREEN  = "\033[92m"
YELLOW = "\033[93m"
CYAN   = "\033[96m"
BOLD   = "\033[1m"
DIM    = "\033[2m"
RESET  = "\033[0m"

class ModeController:
    def __init__(self):
        # Read the default operating mode from config ("MANUAL" or "AUTO")
        self.bot_mode = config.BOT_MODE
        self.client = None
        self.current_balance = 0.0
        self.live_price = 0.0
        self.prev_live_price = 0.0  # Used for visual indicators (Up/Down arrow)
        self.daily_pnl = 0.0 # Placeholder
        
        # State dictionaries holding market data and candles for each timeframe
        # `candles` expects a list of dictionaries with keys: 'color', 'time', etc.
        self.data_5m = {"candles": [], "current_slug": "", "up_token": None, "down_token": None, "market_name": "", "beat_price": 0.0}
        self.data_15m = {"candles": [], "current_slug": "", "up_token": None, "down_token": None, "market_name": "", "beat_price": 0.0}
        
        self.strategy_5m = Strategy5M(base_bet_amount=1.0)
        self.strategy_15m = Strategy15M(base_bet_amount=1.0)
        self.active_strategies = "BOTH"  # "5M", "15M", "BOTH"
        
        self.running = True

    def initialize(self):
        print(f"{GREEN}Initializing Mode Controller...{RESET}")
        self.client = get_client()
        if self.client:
            self.current_balance = check_balance(self.client)
            
    def set_mode(self, mode):
        """Safely switch bot mode."""
        mode = mode.upper()
        if mode not in ["MANUAL", "AUTO"]:
            return False, "Invalid mode"
            
        if mode == "AUTO" and self.bot_mode == "MANUAL":
            if self.current_balance < config.MIN_WALLET_BALANCE:
                return False, f"Cannot activate Auto. Balance ${self.current_balance:.2f} < ${config.MIN_WALLET_BALANCE:.2f}"
            
            # Safe transition
            self.strategy_5m.reset_progression()
            self.strategy_15m.reset_progression()
            
        self.bot_mode = mode
        icon = "🚀" if mode == "AUTO" else "🛑"
        return True, f"{icon} Auto Bot Mode is now set to: {mode}"

    def set_strategies_mode(self, mode):
        """Set which strategies are active: 5M, 15M, or BOTH."""
        mode = mode.upper()
        if mode not in ["5M", "15M", "BOTH"]:
            return False, "❌ Invalid market mode selected."
        
        self.active_strategies = mode
        self.strategy_5m.enabled = (mode in ["5M", "BOTH"])
        self.strategy_15m.enabled = (mode in ["15M", "BOTH"])
        
        target = "Both 5m & 15m" if mode == "BOTH" else f"{mode} only"
        return True, f"🕒 Market Tracking updated to: {target}"

    def set_base_bet(self, amount):
        """Update base bet amount for both strategies."""
        try:
            val = float(amount)
            if val <= 0: return False, "⚠️ Base bet amount must be positive."
            self.strategy_5m.base_bet_amount = val
            self.strategy_15m.base_bet_amount = val
            return True, f"✅ Base bet successfully set to: ${val}"
        except:
            return False, "❌ Invalid amount entered. Please enter a number."

    def get_dashboard_layout(self):
        """
        Returns the current Rich Layout.
        This provides the data for the main.py `Live` render loop.
        """
        if not hasattr(self, 'dashboard'):
            from dashboard import Dashboard  # type: ignore
            self.dashboard = Dashboard(self)
            
        return self.dashboard.generate_layout()

    def process_cycle(self):
        """Called periodically by the main thread."""
        if self.client:
            self.current_balance = check_balance(self.client)
            if self.strategy_5m.enabled:
                self.strategy_5m.process(self.client, self.data_5m, self.current_balance, self.bot_mode)
            if self.strategy_15m.enabled:
                self.strategy_15m.process(self.client, self.data_15m, self.current_balance, self.bot_mode)
