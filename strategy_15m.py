import config  # type: ignore
import time
from datetime import datetime
from risk_manager import validate_bet  # type: ignore
from execution import place_market_order  # type: ignore

class Strategy15M:
    def __init__(self, mc, base_bet_amount=1.0, martingale_type="LINEAR"):
        self.mc = mc
        self.base_bet_amount = base_bet_amount
        self.martingale_type = martingale_type
        self.martingale_step = 0
        self.active_bet_slug = ""
        self.active_bet_side = ""
        self.active_bet_expiry = 0
        self.active_bet_amount = 0.0
        self.active_shares = 0.0
        self.last_processed_candle = ""
        self.wins = 0
        self.losses = 0
        self.next_planned_bet = "Warming up..."
        self.enabled = True
        
        # Warmup: Bot must observe at least 3 fresh candle changes before auto-betting
        self.candles_observed = 0
        self.is_warmed_up = False
        self.MIN_CANDLES_TO_WARMUP = 3
        
    def reset_progression(self):
        self.martingale_step = 0
        self.active_bet_slug = ""
        self.active_bet_side = ""
        self.active_bet_expiry = 0
        self.active_bet_amount = 0.0
        self.active_shares = 0.0
        self.next_planned_bet = "None"
        # Also reset warmup so bot re-observes candles
        self.candles_observed = 0
        self.is_warmed_up = False
        
    def get_current_bet_amount(self):
        # New progression sequence: [2, 5, 10, 22, 45, 95]
        # Any step beyond index 5 will cap at 95 or loop depending on strategy
        progression = [2.0, 5.0, 10.0, 22.0, 45.0, 95.0]
        idx = min(self.martingale_step, len(progression) - 1)
        return progression[idx]

    # ✅ FIX: Prioritize pre-calculated color from main.py
    def get_true_color(self, candle, beat_price):
        """Returns correct candle color. Prioritizes pre-calculated color."""
        if 'color' in candle:
            return candle['color']
        if beat_price > 0:
            return "GREEN" if candle['close'] > beat_price else "RED"
        return "RED"

    def get_candle_sequence_display(self, candles, beat_price=0):
        """Returns premium horizontal candle trend display for Telegram."""
        if not candles:
            return "No data"
        last_n = candles[-9:] if len(candles) >= 9 else candles

        # Mini Heatmap Trend Line
        icons = []
        for c in last_n:
            true_color = self.get_true_color(c, beat_price)
            if c.get("is_live"):
                icons.append("🔵")
            else:
                icons.append("🟢" if true_color == "GREEN" else "🔴")
        
        trend_line = " ".join(icons)
        
        # Streak detection
        streak_color = self.get_true_color(last_n[-1], beat_price)
        streak = 0
        for x in reversed(last_n):
            if self.get_true_color(x, beat_price) == streak_color:
                streak += 1
            else:
                break
        
        fire = "🔥" if streak >= 3 else ""
        return f"{trend_line} {fire}\n    *⚡️ {streak}x {streak_color} streak*"

    def process(self, client, live_data, current_balance, bot_mode):
        """
        Multi-Martingale Auto-Betting Strategy for 15-minute markets.
        
        RULES:
        1. Wait for 3 consecutive same-color candles
        2. Bet OPPOSITE on the 4th candle
        3. If loss, increase stake (martingale)
        4. If win, reset to base stake
        5. Don't bet if already have an active bet
        6. Don't bet immediately on startup (warmup period)
        """
        if not live_data['candles'] or len(live_data['candles']) < 3:
            self.next_planned_bet = "⏳ Candle data ka wait ho rha..."
            return

        # ✅ FIX: beat_price ek baar fetch karo
        beat_p = live_data.get('beat_price', 0)
            
        last_candle_time = live_data['candles'][-1]['time']
        
        # ──── WARMUP LOGIC ────
        if not self.is_warmed_up:
            if self.last_processed_candle and self.last_processed_candle != last_candle_time:
                self.candles_observed += 1
            if self.candles_observed >= self.MIN_CANDLES_TO_WARMUP:
                self.is_warmed_up = True
                print(f"\033[92m[15m] Warmup complete! Auto-betting is now active.\033[0m")
            else:
                remaining = self.MIN_CANDLES_TO_WARMUP - self.candles_observed
                self.next_planned_bet = f"⏳ Tayyari ho rhi ({remaining} candle baaki)"
                self.last_processed_candle = last_candle_time
                return
        
        # ──── WIN/LOSS CHECK ────
        now = time.time()
        if self.active_bet_slug and now > (self.active_bet_expiry + 30):
            prev_candle = live_data['candles'][-1]
            
            won = False
            if self.active_bet_side == "UP":
                won = prev_candle['close'] > beat_p
            else:
                won = prev_candle['close'] < beat_p
                  
            bet_direction = self.active_bet_side
            
            if won:
                self.wins += 1
                payout = self.active_shares
                if config.DRY_RUN:
                    self.mc.update_virtual_pnl(payout, is_win=True)
                
                net_pnl = payout - self.active_bet_amount
                self.mc.add_trade("15m", bet_direction, self.active_bet_amount, "WIN", net_pnl)
                    
                self.martingale_step = 0
                self.active_bet_slug = ""
                self.active_bet_side = ""
                self.active_bet_expiry = 0
                self.active_bet_amount = 0.0
                self.active_shares = 0.0
                from telegram_bot import send_telegram_notification  # type: ignore
                send_telegram_notification(
                    f"🏆 **WIN! (15m)**\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
                    f"🎯 **Side:** `{bet_direction}`\n"
                    f"💰 **Payout:** `+${payout:.2f}`\n"
                    f"📈 **PnL:** `+${net_pnl:.2f}`\n"
                    f"──────────────────\n"
                    f"💳 **Balance:** `${self.mc.current_balance:,.2f}`\n"
                    f"✅ **W:** `{self.wins}` | ❌ **L:** `{self.losses}`"
                )
            else:
                self.losses += 1
                loss_amount = self.active_bet_amount
                self.mc.add_trade("15m", bet_direction, loss_amount, "LOSS", -loss_amount)
                
                self.martingale_step += 1
                if self.martingale_step >= config.MAX_PROGRESSION_STEPS:
                    self.martingale_step = 0
                next_stake = self.get_current_bet_amount()
                self.active_bet_slug = ""
                self.active_bet_side = ""
                self.active_bet_expiry = 0
                self.active_bet_amount = 0.0
                self.active_shares = 0.0
                from telegram_bot import send_telegram_notification  # type: ignore
                send_telegram_notification(
                    f"🔴 **LOSS (15m)**\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
                    f"🎯 **Side:** `{bet_direction}`\n"
                    f"💸 **Lost:** `-${loss_amount:.2f}`\n"
                    f"──────────────────\n"
                    f"💳 **Balance:** `${self.mc.current_balance:,.2f}`\n"
                    f"➡️ **Next:** `${next_stake:.2f}` (Step {self.martingale_step + 1})"
                )

        # ──── ACTIVE BET GUARD ────
        if self.active_bet_slug:
            self.next_planned_bet = f"⏳ Bet chal rhi {self.active_bet_side} pe, wait kro..."
            self.last_processed_candle = last_candle_time
            return

        # ──── SIGNAL DETECTION (3-CANDLE PATTERN) ────
        # ✅ FIX: slice badal diya taaki live candle exclude ho (always last 3 CLOSED candles)
        closed_candles = live_data['candles'][:-1] if live_data['candles'][-1].get("is_live") else live_data['candles']
        last3 = [self.get_true_color(c, beat_p) for c in closed_candles[-3:]]
        signal = ""
        if all(x == "RED" for x in last3):
            signal = "UP"    # 3 RED → bet GREEN (UP)
        elif all(x == "GREEN" for x in last3):
            signal = "DOWN"  # 3 GREEN → bet RED (DOWN)
            
        amount = self.get_current_bet_amount()
        
        if signal:
            direction = "🟢 GREEN" if signal == "UP" else "🔴 RED"
            self.next_planned_bet = f"{direction} ${amount:.2f} (Step {self.martingale_step + 1})"
        else:
            seq = self.get_candle_sequence_display(live_data['candles'], beat_p)  # ✅ FIX
            self.next_planned_bet = f"👀 Dekh rhe: {seq}"

        if self.last_processed_candle == last_candle_time:
            return

        if signal and bot_mode == "AUTO":
            is_valid, reason = validate_bet(amount, current_balance)
            if not is_valid:
                self.next_planned_bet = f"⚠️ Risk limit: {reason}"
            else:
                token_id = live_data['up_token'] if signal == "UP" else live_data['down_token']
                
                if not token_id:
                    self.next_planned_bet = "⚠️ Market data abhi ready nhi"
                    self.last_processed_candle = last_candle_time
                    return
                
                result = place_market_order(client, token_id, amount, signal)
                success = result[0] if isinstance(result, tuple) else result
                order_details = result[1] if isinstance(result, tuple) and len(result) > 1 else {}
                
                if success:
                    self.active_bet_slug = live_data['current_slug']
                    self.active_bet_side = signal
                    self.active_bet_amount = float(amount)
                    self.active_shares = float(order_details.get("shares_acquired") or (amount / 0.50))
                    
                    if config.DRY_RUN:
                        self.mc.update_virtual_pnl(-amount, stake=amount)
                        
                    now_ts = int(time.time())
                    self.active_bet_expiry = ((now_ts // 900) + 1) * 900
                        
                    side_name = order_details.get('side_name', signal) if isinstance(order_details, dict) else signal
                    price_str = f"{order_details.get('avg_price', 0):.4f}" if isinstance(order_details, dict) else "N/A"
                    shares_str = f"{order_details.get('shares_acquired', 0):.2f}" if isinstance(order_details, dict) else "N/A"
                    
                    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    seq_display = self.get_candle_sequence_display(live_data['candles'], beat_p)  # ✅ FIX
                    
                    notif_msg = (
                        f"💎 **OGBot Premium Signal (15m)**\n"
                        f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
                        f"📊 **Market Trend:**\n    {seq_display}\n\n"
                        f"🚀 **Action:** `{signal}` (Reversal)\n"
                        f"──────────────────\n"
                        f"💰 **Stake:** `${amount:.2f}` (Step {self.martingale_step + 1})\n"
                        f"🎯 **Target:** `{price_str}`\n"
                        f"📈 **Shares:** `{shares_str}`\n"
                        f"──────────────────\n"
                        f"🕒 `{now_str}`"
                    )
                    send_telegram_notification(notif_msg)
                    
            self.last_processed_candle = last_candle_time
        elif not signal:
            self.last_processed_candle = last_candle_time