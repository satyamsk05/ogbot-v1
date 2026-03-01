import config  # type: ignore
from risk_manager import validate_bet  # type: ignore
from execution import place_market_order  # type: ignore

class Strategy5M:
    def __init__(self, base_bet_amount=1.0):
        self.base_bet_amount = base_bet_amount
        self.martingale_step = 0
        self.active_bet_slug = ""
        self.active_bet_side = ""
        self.last_processed_candle = ""
        self.wins = 0
        self.losses = 0
        self.next_planned_bet = "None"
        
    def reset_progression(self):
        self.martingale_step = 0
        self.active_bet_slug = ""
        self.active_bet_side = ""
        self.next_planned_bet = "None"
        
    def get_current_bet_amount(self):
        # 3x progression
        return self.base_bet_amount * (3 ** self.martingale_step)

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
        if self.active_bet_slug and self.active_bet_slug != live_data['current_slug']:
            prev_candle = live_data['candles'][-1]
            won = (self.active_bet_side == "UP" and prev_candle['color'] == "GREEN") or \
                  (self.active_bet_side == "DOWN" and prev_candle['color'] == "RED")
                  
            if won:
                self.wins += 1
                self.reset_progression()
                from telegram_bot import send_telegram_notification  # type: ignore
                send_telegram_notification(f"🏆 *Trade Won! (5m)*\n\n*Market:* `{self.active_bet_slug}`\n*Direction:* {self.active_bet_side}")
            else:
                self.losses += 1
                self.martingale_step += 1
                if self.martingale_step >= config.MAX_PROGRESSION_STEPS:
                    self.martingale_step = 0 # Safety reset if max hit
                from telegram_bot import send_telegram_notification  # type: ignore
                send_telegram_notification(f"💔 *Trade Lost (5m)*\n\n*Market:* `{self.active_bet_slug}`\n*Direction:* {self.active_bet_side}\n*Martingale Step:* {self.martingale_step}")
            
            self.active_bet_slug = ""
            self.active_bet_side = ""

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
                success = place_market_order(client, token_id, amount, signal)
                if success:
                    self.active_bet_slug = live_data['current_slug']
                    self.active_bet_side = signal
                    
            # Mark as processed whether order succeeded or failed/skipped to prevent spamming
            self.last_processed_candle = last_candle_time
        elif not signal:
            # Mark processed to avoid unnecessary checks
            self.last_processed_candle = last_candle_time
