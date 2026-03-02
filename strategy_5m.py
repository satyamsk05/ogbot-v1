import config  # type: ignore
import time
from datetime import datetime
from risk_manager import validate_bet  # type: ignore
from execution import place_market_order  # type: ignore

class Strategy5M:
    def __init__(self, base_bet_amount=1.0, martingale_type="LINEAR"):
        self.base_bet_amount = base_bet_amount
        self.martingale_type = martingale_type
        self.martingale_step = 0
        self.active_bet_slug = ""
        self.active_bet_side = ""
        self.active_bet_expiry = 0
        self.last_processed_candle = ""
        self.wins = 0
        self.losses = 0
        self.next_planned_bet = "None"
        self.enabled = True
        
    def reset_progression(self):
        self.martingale_step = 0
        self.active_bet_slug = ""
        self.active_bet_side = ""
        self.active_bet_expiry = 0
        self.next_planned_bet = "None"
        
    def get_current_bet_amount(self):
        if self.martingale_type == "TRIPLE":
            # Triple progression: 1, 3, 9, 27, 81...
            return self.base_bet_amount * (3 ** self.martingale_step)
        else:
            # Linear progression: 1, 2, 3, 4, ...
            return self.base_bet_amount * (self.martingale_step + 1)

    def process(self, client, live_data, current_balance, bot_mode):
        """
        live_data format:
        {
            "candles": [...],
            "current_slug": "btc-updown-5m-...",
            "up_token": "...",
            "down_token": "..."
        }
        """
        if not live_data['candles'] or len(live_data['candles']) < 2:
            self.next_planned_bet = "None"
            return
            
        last_candle_time = live_data['candles'][-1]['time']
        
        # Check if we won/lost the previous bet
        now = time.time()
        if self.active_bet_slug and now > (self.active_bet_expiry + 30):
            # 30s buffer after expiry to let API update
            prev_candle = live_data['candles'][-1]
            # Use beat_price vs current candle if available for better accuracy
            beat_p = live_data.get('beat_price', 0)
            
            won = False
            if self.active_bet_side == "UP":
                won = prev_candle['close'] > beat_p
            else:
                won = prev_candle['close'] < beat_p
                  
            if won:
                self.wins += 1
                self.reset_progression()
                from telegram_bot import send_telegram_notification  # type: ignore
                send_telegram_notification(f"🏆 *Trade Won! (5m)*\n\n*Market:* `{self.active_bet_slug}`\n*Direction:* {self.active_bet_side}")
            else:
                self.losses += 1
                self.martingale_step += 1
                if self.martingale_step >= config.MAX_PROGRESSION_STEPS:
                    self.martingale_step = 0 
                from telegram_bot import send_telegram_notification  # type: ignore
                send_telegram_notification(f"💔 *Trade Lost (5m)*\n\n*Market:* `{self.active_bet_slug}`\n*Direction:* {self.active_bet_side}\n*Martingale Step:* {self.martingale_step}")
            
            self.active_bet_slug = ""
            self.active_bet_side = ""
            self.active_bet_expiry = 0

        # Determine signal based on rules: 5m: two RED -> bet GREEN (UP)
        last2 = [c['color'] for c in live_data['candles'][-2:]]
        signal = ""
        if all(x == "RED" for x in last2):
            signal = "UP"
            
        amount = self.get_current_bet_amount()
        
        if signal:
            self.next_planned_bet = f"{'GREEN' if signal == 'UP' else 'RED'} ${amount:.2f}"
        else:
            self.next_planned_bet = "None"

        # If we have already processed this candle, return
        if self.last_processed_candle == last_candle_time:
            return

        if signal and bot_mode == "AUTO":
            # Check risk limits safely
            is_valid, reason = validate_bet(amount, current_balance)
            if not is_valid:
                # Can't bet due to risk limits
                pass
            else:
                token_id = live_data['up_token'] if signal == "UP" else live_data['down_token']
                
                # Call place_market_order and get detailed results
                success, order_details = place_market_order(client, token_id, amount, signal)
                
                if success:
                    self.active_bet_slug = live_data['current_slug']
                    self.active_bet_side = signal
                    # Store expiry timestamp
                    try:
                        self.active_bet_expiry = int(float(self.active_bet_slug.split('-')[-1]))
                    except:
                        self.active_bet_expiry = int(time.time() + 300)
                        
                    # Extract details for notification
                    side_name = order_details.get('side_name', signal)
                    price_str = f"{order_details.get('avg_price', 0):.4f}"
                    shares_str = f"{order_details.get('shares_acquired', 0):.2f}"
                    
                    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    
                    # Send Telegram notification with detailed info
                    from telegram_bot import send_telegram_notification  # type: ignore
                    notif_msg = (
                        f"🤖 *Auto Trade Placed (5m)*\n\n"
                        f"⏱ *Time:* `{now_str}`\n"
                        f"📦 *Market:* `{self.active_bet_slug}`\n"
                        f"💰 *Stake:* `${amount:.2f}`\n"
                        f"🎯 *Side:* `{side_name}`\n"
                        f"💵 *Avg Price:* `{price_str}`\n"
                        f"📊 *Shares Acquired:* `{shares_str}`\n"
                        f"🏷 *Token:* `{token_id[:8]}...{token_id[-8:]}`\n"
                        f"🔢 *Step:* {self.martingale_step + 1}"
                    )
                    send_telegram_notification(notif_msg)
                    
            # Mark as processed whether order succeeded or failed/skipped to prevent spamming
            self.last_processed_candle = last_candle_time
        elif not signal:
            # Mark processed to avoid unnecessary checks
            self.last_processed_candle = last_candle_time
