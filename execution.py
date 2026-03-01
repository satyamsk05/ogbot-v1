import time
from py_clob_client.client import ClobClient
from py_clob_client.clob_types import MarketOrderArgs, OrderType, ApiCreds, BalanceAllowanceParams, AssetType
from py_clob_client.order_builder.constants import BUY
from py_clob_client.constants import POLYGON

import config  # type: ignore

def get_client():
    if not config.PRIVATE_KEY:
        print("\033[91mError: PRIVATE_KEY not found in .env\033[0m")
        return None
    try:
        client = ClobClient(
            config.HOST,
            key=config.PRIVATE_KEY,
            chain_id=POLYGON,
            signature_type=config.SIGNATURE_TYPE,
            funder=config.POLY_FUNDER if config.POLY_FUNDER else None,
        )
        creds = client.create_or_derive_api_creds()
        client.set_api_creds(creds)
        return client
    except Exception as e:
        print(f"\033[91mClient connect fail: {e}\033[0m")
        return None

def check_balance(client):
    if not client:
        return 0.0
    try:
        params = BalanceAllowanceParams(asset_type=AssetType.COLLATERAL, signature_type=config.SIGNATURE_TYPE)
        client.update_balance_allowance(params)
        resp = client.get_balance_allowance(params)
        raw = resp.get("balance") or 0
        bal = float(raw) / 1e6
        return bal
    except Exception as e:
        print(f"\033[93mWarning: Failed to fetch balance: {e}\033[0m")
        return 0.0

def place_market_order(client, token_id, amount, side_name):
    """
    Executes a market order on Polymarket.
    Returns True on success, False on failure.
    """
    if config.DRY_RUN:
        print(f"\033[96m[DRY RUN] Would place ${amount} on {side_name} (token: {token_id})\033[0m")
        return True
        
    if not client:
        print("\033[91mError: Client not initialized\033[0m")
        return False
        
    if not token_id:
        print(f"\033[91mError: Token ID for {side_name} not provided\033[0m")
        return False

    try:
        order = client.create_market_order(MarketOrderArgs(
            token_id=token_id,
            amount=amount,
            side=BUY,
            price=0.99  # Worst acceptable price for a BUY market order
        ))
        
        resp = client.post_order(order, orderType="FOK")
        
        if resp.get("success"):
            order_id = resp.get("orderID")
            price_str = "Market Price"
            shares_str = "Unknown"
            
            try:
                # Attempt to fetch exact execution details
                if order_id:
                    time.sleep(1) # Wait for matching engine to settle the FOK order
                    order_details = client.get_order(order_id)
                    size_matched = float(order_details.get("size_matched", 0))
                    if size_matched > 0:
                        avg_price = amount / size_matched
                        price_str = f"${avg_price:.3f}"
                        shares_str = f"{size_matched:.2f}"
            except Exception as e:
                print(f"[Warn] Could not fetch exact execution price: {e}")
                
            from datetime import datetime
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                
            success_msg = f"\033[92mOrder Placed Successfully! (${amount} on {side_name} @ {price_str})\033[0m"
            print(success_msg)
            
            from telegram_bot import send_telegram_notification  # type: ignore
            notif_msg = (
                f"✅ *Trade Executed*\n\n"
                f"⏱ *Time:* `{now_str}`\n"
                f"💰 *Stake:* `${amount:.2f}`\n"
                f"📈 *Direction:* `{side_name}`\n"
                f"💵 *Avg Price:* `{price_str}`\n"
                f"📊 *Shares Acquired:* `{shares_str}`\n"
                f"🏷 *Token:* `{token_id[:8]}...{token_id[-8:]}`"
            )
            send_telegram_notification(notif_msg)
            return True
        else:
            err_msg = resp.get('error')
            print(f"\033[91mOrder Failed: {err_msg}\033[0m")
            from telegram_bot import send_telegram_notification  # type: ignore
            send_telegram_notification(f"❌ *Trade Failed*\n\n*Reason:* {err_msg}")
            return False
    except Exception as e:
        print(f"\033[91mOrder Error: {e}\033[0m")
        from telegram_bot import send_telegram_notification  # type: ignore
        send_telegram_notification(f"⚠️ *Trade Error*\n\n`{str(e)}`")
        return False

def place_limit_order(client, token_id, amount, price, side_name, is_buy=True):
    """
    Executes a Limit order on Polymarket.
    side_name: UP or DOWN (display only)
    is_buy: True for BUY, False for SELL
    price: Exact limit price (e.g. 0.45)
    amount: How much $ stake to put in
    """
    if config.DRY_RUN:
        action = "BUY" if is_buy else "SELL"
        print(f"\033[96m[DRY RUN] Would place LIMIT {action} for ${amount} on {side_name} at ${price:.3f} (token: {token_id})\033[0m")
        return True
        
    if not client:
        print("\033[91mError: Client not initialized\033[0m")
        return False
        
    if not token_id:
        print(f"\033[91mError: Token ID for {side_name} not provided\033[0m")
        return False

    try:
        from py_clob_client.clob_types import OrderArgs, OrderType
        from py_clob_client.order_builder.constants import BUY, SELL
        
        # In Polymarket, 'size' is the number of shares. For a BUY, amount / price = shares.
        shares = amount / price
        
        # Polymarket Minimum Size Enforcement (Minimum 5 shares for limit orders)
        if shares < 5.0:
            err_msg = f"Order too small. You are trying to trade {shares:.2f} shares, but Polymarket requires a minimum of 5 shares. Try increasing your stake or lowering your price."
            print(f"\033[91m{err_msg}\033[0m")
            from telegram_bot import send_telegram_notification  # type: ignore
            send_telegram_notification(f"❌ *Limit Order Rejected*\n\n{err_msg}")
            return False
            
        action_const = BUY if is_buy else SELL
        
        args = OrderArgs(
            token_id=token_id,
            price=price,
            size=shares,
            side=action_const
        )
        
        signed_order = client.create_order(args)
        resp = client.post_order(signed_order, orderType=OrderType.GTC)
        
        if resp and resp.get("success"):
            order_id = resp.get("orderID")
            action_str = "BOUGHT" if is_buy else "SOLD"
            
            from datetime import datetime
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                
            success_msg = f"\033[92mLimit Order Placed! ({action_str} {shares:.2f} shares of {side_name} @ ${price:.3f} for ${amount:.2f})\033[0m"
            print(success_msg)
            
            from telegram_bot import send_telegram_notification  # type: ignore
            notif_msg = (
                f"✅ *Limit Order Placed*\n\n"
                f"⏱ *Time:* `{now_str}`\n"
                f"🎯 *Action:* `{action_str}`\n"
                f"📈 *Direction:* `{side_name}`\n"
                f"💵 *Limit Price:* `${price:.3f}`\n"
                f"📊 *Shares:* `{shares:.2f}`\n"
                f"💰 *Total Value:* `${amount:.2f}`\n"
                f"🏷 *Token:* `{token_id[:8]}...{token_id[-8:]}`"
            )
            send_telegram_notification(notif_msg)
            return True
        else:
            err_msg = resp.get('error') if resp else "Unknown API Error"
            print(f"\033[91mLimit Order Failed: {err_msg}\033[0m")
            from telegram_bot import send_telegram_notification  # type: ignore
            send_telegram_notification(f"❌ *Limit Order Failed*\n\n*Reason:* {err_msg}")
            return False
    except Exception as e:
        print(f"\033[91mLimit Order Error: {e}\033[0m")
        from telegram_bot import send_telegram_notification  # type: ignore
        send_telegram_notification(f"⚠️ *Limit Trade Error*\n\n`{str(e)}`")
        return False
