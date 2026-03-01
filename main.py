import requests  # type: ignore
import time
import json
import threading
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
            rounded_end = ((now // interval_seconds) + 1) * interval_seconds
            
            up_token = None
            down_token = None
            market_name = ""
            current_slug = ""
            found_market = False
            
            # Check current window and previous in case of slight delay
            for offset in [0, interval_seconds]:
                slug = f"btc-updown-{timeframe}-{rounded_end - offset}"
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
                                break
                except:
                    continue
                    
            target_data = mc.data_5m if timeframe == "5m" else mc.data_15m
            target_data['candles'] = candles
            
            if found_market:
                target_data['up_token'] = up_token
                target_data['down_token'] = down_token
                target_data['market_name'] = market_name
                target_data['current_slug'] = current_slug
                
                # Best approximation for beat price (open of the current forming candle or live price)
                # the forming candle is data[-1]
                forming_open = float(data[-1][1])
                target_data['beat_price'] = forming_open if forming_open > 0 else mc.live_price
            
        except Exception as e:
            # print(f"Data fetch error ({timeframe}): {e}")
            pass
            
        time.sleep(15)

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
