import config  # type: ignore
import time
from datetime import datetime
from risk_manager import validate_bet  # type: ignore
from execution import place_market_order  # type: ignore

class Strategy5M:
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
        if self.martingale_type == "TRIPLE":
            # Triple progression: 1, 3, 9, 27, 81...
            return self.base_bet_amount * (3 ** self.martingale_step)
        else:
            # Linear progression: 1, 2, 3, 4, ...
            return self.base_bet_amount * (self.martingale_step + 1)

    # ✅ FIX: Color ab beat_price se compare hoga, na ki open/close se
    def get_true_color(self, candle, beat_price):
        """Returns correct candle color based on close vs beat_price (Polymarket logic)."""
        if beat_price > 0:
            return "GREEN" if candle['close'] > beat_price else "RED"
        return candle.get('color', 'RED')  # fallback agar beat_price na ho

    def get_candle_sequence_display(self, candles, beat_price=0):
        """Returns premium vertical candle display for Telegram with beat prices."""
        if not candles:
            return "No data"
        last_n = candles[-9:] if len(candles) >= 9 else candles
        
        # Vertical candle list (newest first)
        lines = []
        for c in reversed(last_n):
            true_color = self.get_true_color(c, beat_price)  # ✅ FIX
            icon = "🟩" if true_color == "GREEN" else "🟥"
            bp = c.get('beat_price', beat_price)
            bp_str = f"`${bp:,.2f}`" if bp > 0 else ""
            lines.append(f"    `{c['time']}` {icon} {bp_str}")
        
        # Streak detection
        streak_color = self.get_true_color(last_n[-1], beat_price)  # ✅ FIX
        streak = 0
        for c in reversed(last_n):
            if self.get_true_color(c, beat_price) == streak_color:  # ✅ FIX
                streak += 1
            else:
                break
        
        streak_icon = "🔴" if streak_color == "RED" else "🟢"
        streak_text = f"    {streak_icon} `{streak}x {streak_color}` streak"
        if streak >= 3:
            streak_text += " 🔥"
        
        return "\n".join(lines) + "\n" + streak_text

    def process(self, client, live_data, current_balance, bot_mode):
        """
        Multi-Martingale Auto-Betting Strategy for 5-minute markets.
        
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
                print(f"\033[92m[5m] Warmup complete! Auto-betting is now active.\033[0m")
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
                self.mc.add_trade("5m", bet_direction, self.active_bet_amount, "WIN", net_pnl)
                
                self.martingale_step = 0
                self.active_bet_slug = ""
                self.active_bet_side = ""
                self.active_bet_expiry = 0
                self.active_bet_amount = 0.0
                self.active_shares = 0.0
                from telegram_bot import send_telegram_notification  # type: ignore
                send_telegram_notification(
                    f"🏆🏆 *WIN! (5m)* 🏆🏆\n\n"
                    f"🎯 *Direction:* `{bet_direction}`\n"
                    f"💰 *Payout:* `+${payout:.2f}`\n"
                    f"📈 *Net PnL:* `+${net_pnl:.2f}`\n"
                    f"💳 *Balance:* `${self.mc.current_balance:,.2f}`\n"
                    f"✅ W: `{self.wins}` | ❌ L: `{self.losses}`"
                )
            else:
                self.losses += 1
                loss_amount = self.active_bet_amount
                self.mc.add_trade("5m", bet_direction, loss_amount, "LOSS", -loss_amount)
                
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
                    f"🔴 *LOSS (5m)* 🔴\n\n"
                    f"🎯 *Direction:* `{bet_direction}`\n"
                    f"💸 *Lost:* `-${loss_amount:.2f}`\n"
                    f"💳 *Balance:* `${self.mc.current_balance:,.2f}`\n"
                    f"➡️ *Next:* `${next_stake:.2f}` (Step {self.martingale_step + 1})"
                )

        # ──── ACTIVE BET GUARD ────
        if self.active_bet_slug:
            self.next_planned_bet = f"⏳ Bet chal rhi {self.active_bet_side} pe, wait kro..."
            self.last_processed_candle = last_candle_time
            return

        # ──── SIGNAL DETECTION (3-CANDLE PATTERN) ────
        # ✅ FIX: c['color'] ki jagah get_true_color() use ho raha hai
        last3 = [self.get_true_color(c, beat_p) for c in live_data['candles'][-3:]]
        signal = ""
        if all(x == "RED" for x in last3):
            signal = "UP"    # 3 RED candles → bet GREEN (UP)
        elif all(x == "GREEN" for x in last3):
            signal = "DOWN"  # 3 GREEN candles → bet RED (DOWN)
            
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
                    self.active_bet_expiry = ((now_ts // 300) + 1) * 300
                        
                    side_name = order_details.get('side_name', signal) if isinstance(order_details, dict) else signal
                    price_str = f"{order_details.get('avg_price', 0):.4f}" if isinstance(order_details, dict) else "N/A"
                    shares_str = f"{order_details.get('shares_acquired', 0):.2f}" if isinstance(order_details, dict) else "N/A"
                    
                    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    seq_display = self.get_candle_sequence_display(live_data['candles'], beat_p)  # ✅ FIX
                    
                    from telegram_bot import send_telegram_notification  # type: ignore
                    notif_msg = (
                        f"🤖 *Auto Trade (5m)*\n\n"
                        f"📊 *Pattern:* `{seq_display} → {signal}`\n"
                        f"⏱ *Time:* `{now_str}`\n"
                        f"💰 *Stake:* `${amount:.2f}`\n"
                        f"🎯 *Side:* `{side_name}`\n"
                        f"💵 *Avg Price:* `{price_str}`\n"
                        f"📊 *Shares:* `{shares_str}`\n"
                        f"🔢 *Martingale Step:* {self.martingale_step + 1}"
                    )
                    send_telegram_notification(notif_msg)
                    
            self.last_processed_candle = last_candle_time
        elif not signal:
            self.last_processed_candle = last_candle_time