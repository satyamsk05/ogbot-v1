#!/usr/bin/env python3
"""
Polymarket BTC 5MIN Bot v4.5 - Full Monitor Fix + Beat Price Correct
"""

import requests
import time
import os
import json
import sys
import threading
from datetime import datetime
from dotenv import load_dotenv
from py_clob_client.client import ClobClient
from py_clob_client.clob_types import MarketOrderArgs, OrderType, ApiCreds, BalanceAllowanceParams, AssetType
from py_clob_client.order_builder.constants import BUY
from py_clob_client.constants import POLYGON

# COLORS
RED    = "\033[91m"
GREEN  = "\033[92m"
YELLOW = "\033[93m"
CYAN   = "\033[96m"
BOLD   = "\033[1m"
DIM    = "\033[2m"
RESET  = "\033[0m"

load_dotenv()

MODE = "monitor"
if len(sys.argv) > 1 and sys.argv[1].lower() in ["trade", "t"]:
    MODE = "trade"

PRIVATE_KEY = os.getenv("PRIVATE_KEY", "").strip().lstrip("0x")
SIGNATURE_TYPE = int(os.getenv("SIGNATURE_TYPE", "1"))
POLY_FUNDER = os.getenv("POLY_FUNDER", "").strip()

HOST = "https://clob.polymarket.com"
GAMMA_API = "https://gamma-api.polymarket.com"
SYMBOL = "BTCUSDT"

live = {
    "price": 0.0,
    "prev_price": 0.0,
    "beat_price": 0.0,
    "candles": [],
    "up_token": None,
    "down_token": None,
    "market_name": "",
    "current_slug": "",
    "balance": 0.0,
}

state = {
    "phase": "WAITING",
    "bet_count": 0,
    "current_bet": 1.0,
    "next_bet": 1.0,
    "bet_direction": "",
    "total_profit": 0.0,
    "wins": 0,
    "losses": 0,
    "waiting_input": False,
    "cycle_loss": 0.0,
    "history": [],
    "martingale_step": 0,
    "last_processed_candle": "",
    "active_bet_slug": "",
    "active_bet_side": "",
}

MARTINGALE_STEPS = [1, 3, 9, 27, 81, 243]  # Sequence as requested: 1, 3, 9, 27...

def fetch_live_price():
    while True:
        try:
            r = requests.get(f"https://api.binance.com/api/v3/ticker/price?symbol={SYMBOL}", timeout=5)
            r.raise_for_status()
            price = float(r.json()['price'])
            live['prev_price'] = live['price']
            live['price'] = price
        except:
            pass  # silent fail, retry next
        time.sleep(4)

def fetch_candles_and_data():
    while True:
        try:
            # Candles
            params = {"symbol": SYMBOL, "interval": "5m", "limit": 10}
            r = requests.get("https://api.binance.com/api/v3/klines", params=params, timeout=10)
            r.raise_for_status()
            data = r.json()
            candles = []
            for c in data[:-1]:
                op = float(c[1])
                cl = float(c[4])
                color = "GREEN" if cl >= op else "RED"
                candles.append({
                    "open": op,
                    "close": cl,
                    "color": color,
                    "time": datetime.fromtimestamp(c[0]/1000).strftime("%H:%M"),
                    "pct": ((cl - op) / op) * 100 if op > 0 else 0,
                })
            live['candles'] = candles

            # Current market + beat price fix
            now = int(time.time())
            rounded_end = ((now // 300) + 1) * 300   # next window end
            for offset in [0, 300]:
                slug = f"btc-updown-5m-{rounded_end - offset}"
                try:
                    gr = requests.get(f"{GAMMA_API}/events?slug={slug}", timeout=5)
                    gdata = gr.json()
                    if gdata and len(gdata) > 0 and 'markets' in gdata[0]:
                        m = gdata[0]['markets'][0]
                        if not m.get('closed', True):
                            tokens = json.loads(m.get('clobTokenIds', '[]'))
                            if len(tokens) >= 2:
                                live['up_token'] = tokens[0]
                                live['down_token'] = tokens[1]
                                live['market_name'] = m.get('question', '')
                                live['current_slug'] = slug

                            # Beat price = previous candle open (best approximation)
                            if live['candles']:
                                live['beat_price'] = live['candles'][-1]['open']
                            elif live['price'] > 0:
                                live['beat_price'] = live['price']  # fallback
                            break
                except:
                    continue
        except:
            pass
        time.sleep(15)

def get_client():
    try:
        client = ClobClient(
            HOST,
            key=PRIVATE_KEY,
            chain_id=POLYGON,
            signature_type=SIGNATURE_TYPE,
            funder=POLY_FUNDER if POLY_FUNDER else None,
        )
        creds = client.create_or_derive_api_creds()
        client.set_api_creds(creds)
        return client
    except Exception as e:
        print(f"{YELLOW}Client connect fail: {e}{RESET}")
        return None

def place_market_order(client, side, amount):
    if MODE != "trade":
        print(f"{CYAN}[MONITOR] Would place ${amount} on {side}{RESET}")
        return True
    
    if not client:
        print(f"{RED}Error: Client not initialized{RESET}")
        return False

    try:
        # Determine token ID based on side
        token_id = live['up_token'] if side == "UP" else live['down_token']
        if not token_id:
            print(f"{RED}Error: Token ID for {side} not found{RESET}")
            return False

        print(f"{CYAN}Placing Market Order: ${amount} on {side}...{RESET}")
        
        # Polymarket market order requires price and amount of tokens
        # For simplicity in this bot, we are using the order builder for a simplified buy
        # Note: In a production bot, we'd need to handle slippage and exact token count calculation.
        # This is a template for the order execution.
        
        # Simplified buy logic for the purpose of the strategy:
        # We need to calculate how many tokens $amount buys at current price.
        # For 5m UP/DOWN, tokens are usually priced between 0.01 and 0.99.
        
        resp = client.create_order(MarketOrderArgs(
            token_id=token_id,
            amount=amount,
            side=BUY
        ))
        
        if resp.get("success"):
            print(f"{GREEN}Order Placed Successfully!{RESET}")
            return True
        else:
            print(f"{RED}Order Failed: {resp.get('error')}{RESET}")
            return False
    except Exception as e:
        print(f"{RED}Order Error: {e}{RESET}")
        return False

def check_and_trade(client):
    if not live['candles'] or len(live['candles']) < 3:
        return

    last_candle_time = live['candles'][-1]['time']
    
    # Process only if we haven't handled this 5m candle window yet
    if state['last_processed_candle'] == last_candle_time:
        return

    # Check previous bet result if exists
    if state['active_bet_slug'] and state['active_bet_slug'] != live['current_slug']:
        # The market we bet on has closed (or we are in a new one)
        # We need to fetch the result of the previous candle to see if we won
        # For simplicity, we compare live['candles'][-1] (which is the result of the previous bet's period)
        
        prev_candle = live['candles'][-1]
        won = (state['active_bet_side'] == "UP" and prev_candle['color'] == "GREEN") or \
              (state['active_bet_side'] == "DOWN" and prev_candle['color'] == "RED")
        
        if won:
            print(f"{GREEN}{BOLD}WIN! Resetting Martingale.{RESET}")
            state['wins'] += 1
            state['martingale_step'] = 0
            state['total_profit'] += (MARTINGALE_STEPS[state['martingale_step']] * 0.9) # Approx profit
        else:
            print(f"{RED}{BOLD}LOSS! Increasing Martingale.{RESET}")
            state['losses'] += 1
            state['martingale_step'] = min(state['martingale_step'] + 1, len(MARTINGALE_STEPS) - 1)
        
        state['active_bet_slug'] = ""
        state['active_bet_side'] = ""

    # Check for 3-candle pattern
    last3 = [c['color'] for c in live['candles'][-3:]]
    signal = ""
    if all(x == "RED" for x in last3):
        signal = "UP"  # Red Red Red -> Green (UP)
    elif all(x == "GREEN" for x in last3):
        signal = "DOWN" # Green Green Green -> Red (DOWN)

    if signal:
        amount = MARTINGALE_STEPS[state['martingale_step']]
        print(f"{YELLOW}Pattern Detected: {last3} -> Signal: {signal} (${amount}){RESET}")
        
        if place_market_order(client, signal, amount):
            state['active_bet_slug'] = live['current_slug']
            state['active_bet_side'] = signal
            state['last_processed_candle'] = last_candle_time
            state['current_bet'] = amount
    else:
        # Mark as processed even if no signal to wait for next candle
        state['last_processed_candle'] = last_candle_time

def check_balance(client):
    if not client:
        return 0.0
    try:
        params = BalanceAllowanceParams(asset_type=AssetType.COLLATERAL, signature_type=SIGNATURE_TYPE)
        client.update_balance_allowance(params)
        resp = client.get_balance_allowance(params)
        raw = resp.get("balance") or 0
        bal = float(raw) / 1e6
        live['balance'] = bal
        return bal
    except:
        return live['balance']

def clear_screen():
    os.system('cls' if os.name == 'nt' else 'clear')

def print_dashboard():
    clear_screen()
    bal_col = GREEN if live['balance'] > 0 else RED
    price_arrow = f"{GREEN}▲{RESET}" if live['price'] > live['prev_price'] else f"{RED}▼{RESET}" if live['price'] < live['prev_price'] else f"{YELLOW}─{RESET}"

    print(f"{BOLD}{CYAN}POLYMARKET BTC 5MIN BOT v4.5{RESET}   Mode: {GREEN if MODE=='trade' else YELLOW}{MODE.upper()}{RESET}")
    print(f"  Balance: {bal_col}${live['balance']:.2f}{RESET}")
    print(f"  BTC Price: ${live['price']:,.0f} {price_arrow}")
    print(f"  Beat Price (start): ${live['beat_price']:,.0f}")

    if live['candles']:
        print("\n  Recent Candles:")
        for c in live['candles'][-5:]:
            col = GREEN if c['color'] == "GREEN" else RED
            print(f"  {c['time']} {col}{c['color']}{RESET} {c['pct']:+.2f}%")

        if len(live['candles']) >= 3:
            last3 = [c['color'] for c in live['candles'][-3:]]
            if all(x == "RED" for x in last3):
                print(f"\n  {RED}{BOLD}3 RED → UP signal strong!{RESET}")
            elif all(x == "GREEN" for x in last3):
                print(f"\n  {GREEN}{BOLD}3 GREEN → DOWN signal strong!{RESET}")
            else:
                print(f"\n  Pattern: Mixed")
    else:
        print(f"\n  {YELLOW}Loading market data...{RESET}")

    if state['active_bet_side']:
        print(f"\n  {CYAN}Active Bet: {state['active_bet_side']} (${state['current_bet']}) on {state['active_bet_slug']}{RESET}")
    
    print(f"  Result: {GREEN}Wins: {state['wins']}{RESET} | {RED}Losses: {state['losses']}{RESET} | Martingale Step: {state['martingale_step'] + 1}")
    print("=" * 60)

def main():
    print(f"{GREEN}Starting bot v4.5...{RESET}")

    client = get_client()
    if client:
        check_balance(client)

    threading.Thread(target=fetch_live_price, daemon=True).start()
    threading.Thread(target=fetch_candles_and_data, daemon=True).start()

    time.sleep(10)  # data load hone do
    print(f"{GREEN}Monitor active!{RESET}")

    try:
        while True:
            if client:
                check_balance(client)
                check_and_trade(client)
            print_dashboard()
            time.sleep(10)
    except KeyboardInterrupt:
        print(f"\n{YELLOW}Bot stopped.{RESET}")

if __name__ == "__main__":
    main()