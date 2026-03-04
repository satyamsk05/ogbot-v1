import os
import time
import config  # type: ignore
from datetime import datetime
from execution import get_client, check_balance, redeem_all_funds  # type: ignore
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
        
        self.strategy_5m = Strategy5M(mc=self, base_bet_amount=2.0, martingale_type=config.DEFAULT_MARTINGALE_TYPE)
        self.strategy_15m = Strategy15M(mc=self, base_bet_amount=2.0, martingale_type=config.DEFAULT_MARTINGALE_TYPE)
        self.martingale_type = config.DEFAULT_MARTINGALE_TYPE
        
        # Balance Setup
        self.virtual_balance = config.VIRTUAL_START_BALANCE
        self.current_balance = self.virtual_balance if config.DRY_RUN else 0.0
        self.active_strategies = "BOTH"  # "5M", "15M", "BOTH"
        
        # Simulation Stats
        self.sim_trades = 0
        self.sim_wins = 0
        self.sim_stake = 0.0
        self.sim_slippage = 0.005  # 0.5% default slippage
        self.sim_fees = 0.001      # 0.1% default fees
        
        # Trade History (last 20 trades)
        self.trade_history = []
        self.MAX_HISTORY = 20
        
        # Daily Summary
        self.daily_report_sent = False
        
        self.last_redeem_time = 0
        self.auto_redeem_enabled = True
        self.strike_cache = {} # timestamp -> strike_price
        self.running = True

    def initialize(self):
        print(f"{GREEN}Initializing Mode Controller...{RESET}")
        self.client = get_client()
        if self.client and not config.DRY_RUN:
            self.update_balance(check_balance(self.client))
            
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

    def set_martingale_type(self, m_type):
        """Switch martingale system for both strategies."""
        m_type = m_type.upper()
        if m_type not in ["LINEAR", "TRIPLE"]:
            return False, "❌ Invalid martingale type."
        
        self.martingale_type = m_type
        self.strategy_5m.martingale_type = m_type
        self.strategy_15m.martingale_type = m_type
        
        # Reset progression when changing system
        self.strategy_5m.reset_progression()
        self.strategy_15m.reset_progression()
        
        desc = "Linear ($1, $2, $3)" if m_type == "LINEAR" else "Triple ($1, $3, $9)"
        return True, f"🤖 Betting System set to: {desc}"
        
    def toggle_auto_redeem(self):
        """Toggle the automatic redemption loop."""
        self.auto_redeem_enabled = not self.auto_redeem_enabled
        status = "ENABLED ✅" if self.auto_redeem_enabled else "DISABLED ❌"
        return True, f"🤖 Auto Cashout is now {status}"

    def get_dashboard_layout(self):
        """
        Returns the current Rich Layout.
        This provides the data for the main.py `Live` render loop.
        """
        if not hasattr(self, 'dashboard'):
            from dashboard import Dashboard  # type: ignore
            self.dashboard = Dashboard(self)
            
        return self.dashboard.generate_layout()

    def update_balance(self, balance: float):
        if config.DRY_RUN:
            # In Dry Run, we don't overwrite from external source
            # current_balance is always virtual_balance
            self.current_balance = self.virtual_balance
        else:
            self.current_balance = balance

    def update_virtual_pnl(self, amount: float, is_win: bool = False, stake: float = 0.0):
        """Update virtual balance and notify"""
        if config.DRY_RUN:
            actual_amount = amount
            if stake > 0:
                # Deduct fees on entry
                fee = stake * self.sim_fees
                actual_amount -= fee
                self.sim_stake += stake
                self.sim_trades += 1
            
            if is_win:
                # Apply slippage on exit (payout)
                actual_amount = actual_amount * (1 - self.sim_slippage)
                self.sim_wins += 1
                
            self.virtual_balance += actual_amount
            self.current_balance = self.virtual_balance
            # Update Daily PnL
            self.daily_pnl = self.virtual_balance - config.VIRTUAL_START_BALANCE

    def add_trade(self, timeframe: str, side: str, amount: float, result: str, pnl: float):
        """Add a trade to history"""
        entry = {
            "time": datetime.now().strftime("%H:%M:%S"),
            "tf": timeframe,
            "side": side,
            "amount": amount,
            "result": result,  # "WIN" or "LOSS"
            "pnl": pnl,
            "balance": self.current_balance
        }
        self.trade_history.append(entry)
        if len(self.trade_history) > self.MAX_HISTORY:
            self.trade_history.pop(0)

    def get_daily_summary(self):
        """Generate daily summary text"""
        s5 = self.strategy_5m
        s15 = self.strategy_15m
        total_w = s5.wins + s15.wins
        total_l = s5.losses + s15.losses
        total_t = total_w + total_l
        win_rate = (total_w / total_t * 100) if total_t > 0 else 0
        bal_tag = " [SIM]" if config.DRY_RUN else ""
        pnl_sign = "+" if self.daily_pnl >= 0 else ""
        pnl_icon = "🟢" if self.daily_pnl >= 0 else "🔴"
        
        summary = (
            f"📊 *Daily Summary Report{bal_tag}*\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"{pnl_icon} *PnL:* `{pnl_sign}${self.daily_pnl:,.2f}`\n"
            f"💰 *Balance:* `${self.current_balance:,.2f}`\n\n"
            f"🏆 *Win Rate:* `{win_rate:.1f}%`\n"
            f"✅ *Wins:* `{total_w}`  |  ❌ *Losses:* `{total_l}`\n"
            f"💸 *Total Volume:* `${self.sim_stake:,.2f}`\n\n"
            f"📈 *5m:* W `{s5.wins}` / L `{s5.losses}`\n"
            f"📉 *15m:* W `{s15.wins}` / L `{s15.losses}`\n\n"
            f"🕒 *Report Time:* `{datetime.now().strftime('%Y-%m-%d %H:%M')}`"
        )
        return summary

    def get_trade_history_text(self):
        """Format trade history for Telegram display"""
        if not self.trade_history:
            return "📝 *Trade History*\n\nNo trades yet."
        
        lines = ["📝 *Trade History (Last 20)*\n━━━━━━━━━━━━━━━━━━━━━━━━"]
        for i, t in enumerate(reversed(self.trade_history), 1):
            icon = "✅" if t['result'] == 'WIN' else "❌"
            pnl_sign = "+" if t['pnl'] >= 0 else ""
            lines.append(
                f"`{t['time']}` {icon} {t['tf']} {t['side']} "
                f"`${t['amount']:.2f}` → `{pnl_sign}${t['pnl']:.2f}`"
            )
        return "\n".join(lines)

    def set_virtual_balance(self, amount):
        """Manual reset to custom amount"""
        try:
            val = float(amount)
            self.virtual_balance = val
            self.current_balance = val
            self.daily_pnl = 0.0 # Reset PnL relative to new start
            config.VIRTUAL_START_BALANCE = val # Update baseline
            return True, f"✅ Virtual wallet set to: ${val:.2f}"
        except:
            return False, "❌ Invalid amount."

    def reset_virtual_balance(self):
        """Reset simulation stats and wallet"""
        if config.DRY_RUN:
            self.virtual_balance = config.VIRTUAL_START_BALANCE
            self.current_balance = self.virtual_balance
            self.daily_pnl = 0.0
            self.sim_trades = 0
            self.sim_wins = 0
            self.sim_stake = 0.0
            self.strategy_5m.wins = 0
            self.strategy_5m.losses = 0
            self.strategy_15m.wins = 0
            self.strategy_15m.losses = 0
            return True, "💡 Virtual wallet and stats have been reset to $500."
        return False, "❌ Not in Dry Run mode."

    def process_cycle(self):
        """Called periodically by the main thread."""
        # Allow processing in DRY_RUN even if client initialization failed (e.g. missing PRIVATE_KEY)
        if self.client or config.DRY_RUN:
            # 1. Update Balance & Strategy Processing
            if not config.DRY_RUN and self.client:
                self.update_balance(check_balance(self.client))
            
            if self.strategy_5m.enabled:
                self.strategy_5m.process(self.client, self.data_5m, self.current_balance, self.bot_mode)
            if self.strategy_15m.enabled:
                self.strategy_15m.process(self.client, self.data_15m, self.current_balance, self.bot_mode)
            
            # 2. Periodic Auto-Redemption (Every 3 minutes)
            if self.auto_redeem_enabled and self.client:
                now = time.time()
                if now - self.last_redeem_time > 180:
                    print(f"{CYAN}[System] Triggering periodic auto-redemption...{RESET}")
                    redeem_all_funds(self.client)
                    self.last_redeem_time = int(now)
