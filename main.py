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
import logging

# Setup Logging for Server Deployment
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler(config.LOG_FILE),
        logging.StreamHandler() if not config.HEADLESS else logging.NullHandler()
    ]
)
logger = logging.getLogger(__name__)


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
    Background thread to fetch Binance BTC candle data for chart display.
    """
    import urllib.parse
    while mc.running:
        try:
            target_data = mc.data_5m if timeframe == "5m" else mc.data_15m
            now = int(time.time())
            
            rounded_end = ((now // interval_seconds) + 1) * interval_seconds
            expiry_str = datetime.fromtimestamp(rounded_end, tz=config.ET_TZ).strftime("%I:%M %p")
            target_data['expiry'] = expiry_str

            slug = f"btc-updown-{timeframe}-{rounded_end}"
            
            # 1. Fetch live market token and beat price from Polymarket
            try:
                gr = requests.get(f"{config.GAMMA_API}/events?slug={slug}", timeout=5)
                gdata = gr.json()
                if gdata and len(gdata) > 0 and 'markets' in gdata[0]:
                    m = gdata[0]['markets'][0]
                    target_data['market_name'] = m.get('question', '')
                    target_data['current_slug'] = slug
                    
                    tokens = json.loads(m.get('clobTokenIds', '[]'))
                    if len(tokens) >= 2:
                        target_data['up_token'] = tokens[0]
                        target_data['down_token'] = tokens[1]
                        logger.info(f"[{timeframe}] Tokens loaded for {slug}")
                else:
                    logger.warning(f"[{timeframe}] No market found for slug: {slug}")
            except Exception as e:
                logger.error(f"[{timeframe}] Gamma API Error for {slug}: {e}")
                pass

            # 2. Fetch standard Binance BTC OHLC charts
            try:
                binance_tf = "5m" if timeframe == "5m" else "15m"
                br = requests.get(
                    "https://api.binance.com/api/v3/klines", 
                    params={"symbol": config.SYMBOL, "interval": binance_tf, "limit": 10},
                    timeout=5
                )
                klines = br.json()
                
                candles = []
                for i, k in enumerate(klines):
                    is_live = (i == len(klines) - 1)
                    op = float(k[1])
                    cl = float(k[4])
                    c_start = int(k[0]) // 1000
                    c_end = int(k[6]) // 1000
                    
                    c_obj = {
                        "time": datetime.fromtimestamp(c_start, tz=config.ET_TZ).strftime("%I:%M %p"),
                        "start_ts": c_start,
                        "expiry_ts": c_end,
                        "is_live": is_live,
                        "open": op,
                        "close": cl,
                        "color": "GREEN" if cl >= op else "RED"
                    }
                    
                    if is_live:
                        c_obj["seconds_until_close"] = max(0, rounded_end - now)
                        c_obj["beat_price"] = op
                        target_data['beat_price'] = op
                        
                    candles.append(c_obj)
                    
                target_data['candles'] = candles
            except Exception:
                pass

        except Exception as e:
            pass

        time.sleep(10)


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

    logger.info(f"Starting bot in {'HEADLESS' if config.HEADLESS else 'UI'} mode...")

    try:
        if config.HEADLESS:
            # Simple Headless Loop
            while mc.running:
                current_time = time.time()
                if current_time - last_process_time >= 5:
                    mc.process_cycle()
                    last_process_time = current_time
                    # Enhanced Heartbeat log
                    if int(current_time) % 60 < 5: 
                        s5_status = mc.strategy_5m.next_planned_bet
                        s15_status = mc.strategy_15m.next_planned_bet
                        logger.info(f"Heartbeat: Bal=${mc.current_balance:.2f} | 5m: {s5_status} | 15m: {s15_status}")
                time.sleep(1)
        else:
            # Interactive UI Loop
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
        logger.info("Bot shutting down safely (KeyboardInterrupt).")
    except Exception as e:
        import traceback
        logger.error(f"CRITICAL ERROR: {e}")
        logger.error(traceback.format_exc())
        mc.running = False


if __name__ == "__main__":
    main()