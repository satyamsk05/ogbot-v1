import requests  # type: ignore
import time
import json
import threading
import re
from datetime import datetime

from rich.live import Live  # type: ignore

import config  # type: ignore
from mode_controller import ModeController  # type: ignore
from manual_interface import input_thread_func  # type: ignore
from telegram_bot import run_telegram_bot  # type: ignore


def fetch_live_price(mc):
    """
    Background thread to fetch Binance BTC live price.
    Updated interval to 0.1 seconds for real-time tracking.
    """
    while mc.running:
        try:
            r = requests.get(f"https://api.binance.com/api/v3/ticker/price?symbol={config.SYMBOL}", timeout=5)
            r.raise_for_status()
            mc.prev_live_price = mc.live_price
            mc.live_price = float(r.json()['price'])
        except:
            pass
        time.sleep(0.1)

def fetch_market_data(mc, timeframe="5m", interval_seconds=300):
    """
    ✅ SIMPLE LOGIC:
    - Polymarket se beat_price (price to beat) fetch karo
    - Har candle ka color = close > beat_price ? GREEN : RED
    - Koi complicated cache/overlay nahi
    """
    while mc.running:
        try:
            target_data = mc.data_5m if timeframe == "5m" else mc.data_15m

            # ── STEP 1: Polymarket se current market aur beat_price fetch karo ──
            now = int(time.time())
            rounded_end = ((now // interval_seconds) + 1) * interval_seconds
            target_timestamp = rounded_end
            if (rounded_end - now) > 60:
                target_timestamp = rounded_end - interval_seconds

            beat_price = float(target_data.get('beat_price', 0.0))  # pehle se jo hai wo rakho
            up_token = None
            down_token = None
            market_name = ""
            current_slug = ""

            for ts in [target_timestamp, target_timestamp + interval_seconds]:
                slug = f"btc-updown-{timeframe}-{ts}"
                try:
                    gr = requests.get(f"{config.GAMMA_API}/events?slug={slug}", timeout=5)
                    gdata = gr.json()
                    if gdata and len(gdata) > 0 and 'markets' in gdata[0]:
                        m = gdata[0]['markets'][0]
                        if not m.get('closed', True):
                            tokens = json.loads(m.get('clobTokenIds', '[]'))
                            if len(tokens) >= 2:
                                up_token = tokens[0]
                                down_token = tokens[1]
                                market_name = m.get('question', '')
                                current_slug = slug
                                expiry_str = datetime.fromtimestamp(ts, tz=config.ET_TZ).strftime("%I:%M %p")
                                target_data['expiry'] = expiry_str

                                # ✅ beat_price market question se nikalo: "Will BTC be above $68,207.82"
                                match = re.search(r'\$([0-9,.]+)', market_name)
                                if match:
                                    beat_price = float(match.group(1).replace(',', ''))
                                break
                except:
                    continue

            # beat_price update karo
            if beat_price > 0.0:
                target_data['beat_price'] = beat_price
            if up_token:
                target_data['up_token'] = up_token
                target_data['down_token'] = down_token
                target_data['market_name'] = market_name
                target_data['current_slug'] = current_slug

            # ── STEP 2: Binance se candles fetch karo (price data ke liye) ──
            params = {"symbol": config.SYMBOL, "interval": timeframe, "limit": 10}
            r = requests.get("https://api.binance.com/api/v3/klines", params=params, timeout=10)
            r.raise_for_status()
            data = r.json()

            # ── STEP 3: ✅ SIMPLE COLOR LOGIC: close > beat_price = GREEN, warna RED ──
            bp = target_data.get('beat_price', 0)
            candles = []
            
            # interval in seconds (5m=300, 15m=900)
            interval_sec = 300 if timeframe == "5m" else 900
            
            for i, c in enumerate(data):
                op = float(c[1])
                cl = float(c[4])
                start_ts = int(int(c[0]) // 1000)
                expiry_ts = int(start_ts + int(interval_sec))
                
                is_live = (i == len(data) - 1)
                
                if bp > 0:
                    color = "GREEN" if cl > bp else "RED"
                else:
                    color = "GREEN" if cl >= op else "RED"

                candle_obj = {
                    "open": op,
                    "close": cl,
                    "color": color,
                    "beat_price": bp,
                    "time": datetime.fromtimestamp(expiry_ts, tz=config.ET_TZ).strftime("%I:%M %p"),
                    "start_ts": start_ts,
                    "expiry_ts": expiry_ts,
                    "is_live": is_live
                }
                
                if is_live:
                    now_ts = int(time.time())
                    secs_left = max(0, expiry_ts - now_ts)
                    candle_obj["seconds_until_close"] = secs_left
                
                candles.append(candle_obj)

            target_data['candles'] = candles

        except Exception as e:
            pass

        time.sleep(5)


def daily_summary_scheduler(mc):
    """Send daily summary at 23:59 and reset stats"""
    from telegram_bot import send_telegram_notification  # type: ignore
    while mc.running:
        now = datetime.now()
        if now.hour == 23 and now.minute == 59 and not mc.daily_report_sent:
            try:
                summary = mc.get_daily_summary()
                send_telegram_notification(summary)
                mc.daily_report_sent = True
            except Exception as e:
                print(f"[Daily Report Error]: {e}")
        elif now.hour == 0 and now.minute == 0 and mc.daily_report_sent:
            mc.daily_report_sent = False
        time.sleep(30)


def main():
    print("Starting Polymarket dual-mode bot...")
    mc = ModeController()
    mc.initialize()

    threading.Thread(target=fetch_live_price, args=(mc,), daemon=True).start()
    threading.Thread(target=fetch_market_data, args=(mc, "5m", 300), daemon=True).start()
    threading.Thread(target=fetch_market_data, args=(mc, "15m", 900), daemon=True).start()
    threading.Thread(target=input_thread_func, args=(mc,), daemon=True).start()
    threading.Thread(target=run_telegram_bot, args=(mc,), daemon=True).start()
    threading.Thread(target=daily_summary_scheduler, args=(mc,), daemon=True).start()

    time.sleep(5)

    last_process_time = 0.0

    try:
        with Live(mc.get_dashboard_layout(), refresh_per_second=5, screen=True) as live:
            while mc.running:
                current_time = time.time()

                if current_time - last_process_time >= 5:
                    mc.process_cycle()
                    last_process_time = current_time

                live.update(mc.get_dashboard_layout())
                time.sleep(0.2)

    except KeyboardInterrupt:
        mc.running = False
        print("\nBot shutting down safely...")
    except Exception as e:
        import traceback
        traceback.print_exc()
        mc.running = False
        print(f"\n[CRITICAL ERROR] UI Loop Crashed: {e}")


if __name__ == "__main__":
    main()