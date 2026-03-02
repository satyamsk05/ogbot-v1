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
            
            # Store previous price to determine trend direction (up/down)
            mc.prev_live_price = mc.live_price
            mc.live_price = float(r.json()['price'])
        except:
            pass
        time.sleep(0.1)  # Faster updates (0.1s)

def fetch_market_data(mc, timeframe="5m", interval_seconds=300):
    """
    Fetches Binance candles and Polymarket Gamma API data for the given timeframe.
    """
    while mc.running:
        try:
            # 1. Fetch Binance Candles
            params = {"symbol": config.SYMBOL, "interval": timeframe, "limit": 10}
            r = requests.get("https://api.binance.com/api/v3/klines", params=params, timeout=10)
            r.raise_for_status()
            data = r.json()
            
            candles = []
            for c in data[:-1]: # exclude the currently forming candle
                op = float(c[1])
                cl = float(c[4])
                color = "GREEN" if cl >= op else "RED"
                candles.append({
                    "open": op,
                    "close": cl,
                    "color": color,
                    "time": datetime.fromtimestamp(c[0]/1000).strftime("%H:%M"),
                })
                
            # 2. Fetch Polymarket Gamma Data
            now = int(time.time())
            # The window ends every 300s (5m) or 900s (15m)
            rounded_end = ((now // interval_seconds) + 1) * interval_seconds
            
            # Buffer: Only switch to the NEXT market if there's < 60 seconds left in current one
            target_timestamp = rounded_end
            if (rounded_end - now) > 60:
                target_timestamp = rounded_end - interval_seconds
                
            up_token = None
            down_token = None
            market_name = ""
            current_slug = ""
            found_market = False
            
            target_data = mc.data_5m if timeframe == "5m" else mc.data_15m
            target_data['candles'] = candles

            # Check target window and the one after it
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
                                found_market = True
                                expiry_str = datetime.fromtimestamp(ts).strftime("%H:%M")
                                target_data['expiry'] = expiry_str
                                break
                except:
                    continue
                    
            if found_market:
                target_data['up_token'] = up_token
                target_data['down_token'] = down_token
                target_data['market_name'] = market_name
                target_data['current_slug'] = current_slug
                
                # Best approximation for beat price (Try Question first, then forming candle)
                beat_price = 0.0
                try:
                    # Parse "$66,756.99" from "Will BTC be above $66,756.99..."
                    match = re.search(r'\$([0-9,.]+)', market_name)
                    if match:
                        beat_price = float(match.group(1).replace(',', ''))
                except:
                    pass
                
                if beat_price == 0.0 and data:
                    # Fallback to forming candle's open price
                    beat_price = float(data[-1][1])
                
                target_data['beat_price'] = beat_price if beat_price > 0 else mc.live_price
                
        except Exception as e:
            # print(f"Fetch error: {e}")
            pass
            
        time.sleep(5)  # Fast refresh: 5 seconds

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
            # Reset flag at midnight for next day
            mc.daily_report_sent = False
        time.sleep(30)  # Check every 30 seconds

def main():
    print("Starting Polymarket dual-mode bot...")
    mc = ModeController()
    mc.initialize()
    
    # Start background threads
    threading.Thread(target=fetch_live_price, args=(mc,), daemon=True).start()
    threading.Thread(target=fetch_market_data, args=(mc, "5m", 300), daemon=True).start()
    threading.Thread(target=fetch_market_data, args=(mc, "15m", 900), daemon=True).start()
    
    # Start manual input listener thread handling terminal CLI
    threading.Thread(target=input_thread_func, args=(mc,), daemon=True).start()
    
    # Start Telegram bot listener thread
    threading.Thread(target=run_telegram_bot, args=(mc,), daemon=True).start()
    
    # Start daily summary scheduler
    threading.Thread(target=daily_summary_scheduler, args=(mc,), daemon=True).start()
    
    # Give threads a moment to fetch initial data
    time.sleep(5)
    
    # Main loop for processing strategies and UI
    # We decouple dashboard rendering to run faster while strategies run slower
    last_process_time = 0.0
    
    try:
        # Wrap the continuous loop inside the Rich Live UI context
        with Live(mc.get_dashboard_layout(), refresh_per_second=5, screen=True) as live:
            while mc.running:
                current_time = time.time()
                
                # Process strategies every 5 seconds (avoid spamming API)
                if current_time - last_process_time >= 5:
                    mc.process_cycle()
                    last_process_time = current_time
                
                # Update the Rich Live Display layout
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
