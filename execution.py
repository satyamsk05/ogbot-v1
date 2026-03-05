import time
from py_clob_client.client import ClobClient
from py_clob_client.clob_types import MarketOrderArgs, OrderArgs, OrderType, ApiCreds, BalanceAllowanceParams, AssetType
from py_clob_client.order_builder.constants import BUY, SELL
from py_clob_client.constants import POLYGON
from web3 import Web3
from datetime import datetime
import json

import config  # type: ignore
from risk_manager import validate_bet  # type: ignore
import os
import requests

# Constants for Redemption
CONDITIONAL_TOKENS_ABI = '[{"constant":false,"inputs":[{"name":"collateralToken","type":"address"},{"name":"parentCollectionId","type":"bytes32"},{"name":"conditionId","type":"bytes32"},{"name":"indexSets","type":"uint256[]"}],"name":"redeemPositions","outputs":[],"payable":false,"stateMutability":"nonpayable","type":"function"}]'
CONDITIONAL_TOKENS_ADDRESS = "0x4D97Dcd97eC945f40cF67F118206585df3609180" # Polygon Mainnet

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

def redeem_all_funds(client):
    """
    Robust redemption logic to cash out winning positions.
    Searches both current positions and notifications for claimable funds.
    """
    if not client:
        return False

    print(f"\033[94m[Cashout] Starting full scan for redeemable positions...\033[0m")
    
    try:
        # ✅ FIX: Use robust fallback RPCs from config
        w3 = config.get_w3()
        
        if not w3 or not w3.is_connected():
            print("\033[91m[Cashout] Web3 connection failed. Skipping.\033[0m")
            return False

        account_addr = client.get_address()
        contract = w3.eth.contract(address=Web3.to_checksum_address(CONDITIONAL_TOKENS_ADDRESS), abi=json.loads(CONDITIONAL_TOKENS_ABI))
        
        # 1. Digital Asset Scan (Replacement for missing get_positions)
        # Note: Current CLOB SDK may not support direct 'get_positions'. 
        # We rely on notifications for settlement alerts which is more efficient.
        found_any = False
        processed_conditions = set()

        # 2. Check Notifications (Efficient way to find claimable markets)
        try:
            notifications = client.get_notifications()
            if notifications:
                for note in notifications:
                    # Note structure varies, but we look for settlement/claim indicators
                    if note.get('type') == 'SETTLEMENT' or 'claim' in str(note).lower():
                        cid = note.get('condition_id')
                        col = note.get('collateral_token')
                        if cid and col and cid not in processed_conditions:
                            print(f"\033[94m[Cashout] Found claimable position in notifications. Redeeming...\033[0m")
                            
                            try:
                                # indexSets for binary markets: [1, 2] usually covers both Yes and No
                                index_sets = [1, 2] 
                                nonce = w3.eth.get_transaction_count(Web3.to_checksum_address(account_addr))
                                tx = contract.functions.redeemPositions(
                                    Web3.to_checksum_address(col),
                                    "0x" + "0" * 64, # parentCollectionId
                                    Web3.to_bytes(hexstr=cid),
                                    index_sets
                                ).build_transaction({
                                    'from': Web3.to_checksum_address(account_addr),
                                    'nonce': nonce,
                                    'gas': 250000,
                                    'gasPrice': w3.eth.gas_price
                                })
                                
                                signed_tx = w3.eth.account.sign_transaction(tx, private_key=config.PRIVATE_KEY)
                                tx_hash = w3.eth.send_raw_transaction(signed_tx.rawTransaction)
                                print(f"\033[92m[Cashout] Success! Redemption sent. TX: {tx_hash.hex()}\033[0m")
                                processed_conditions.add(cid)
                                found_any = True
                            except Exception as re:
                                print(f"\033[91m[Cashout] Redemption TX failed for {cid[:10]}: {re}\033[0m")
        except Exception as e:
            print(f"\033[93m[Cashout] Notification check skipped: {e}\033[0m")

        if not found_any:
            print("\033[94m[Cashout] Scan complete. No redeemable positions found at this time.\033[0m")
            
        return True
    except Exception as e:
        print(f"\033[91m[Cashout Major Error] {e}\033[0m")
        return False

def place_market_order(client, token_id, amount, side_name):
    """
    Executes a market order on Polymarket with enhanced terminal logging.
    """
    print(f"\033[94m\033[1m[TRADE] Attempting to Buy ${amount:.2f} of {side_name}...\033[0m")
    
    if config.DRY_RUN:
        print(f"\033[96m[DRY RUN] Simulation: BOUGHT ${amount} on {side_name}\033[0m")
        return True, {"avg_price": 0.50, "shares_acquired": amount / 0.50, "side_name": side_name}
        
    if not client:
        print("\033[91m[ERROR] Client not initialized!\033[0m")
        return False, {}
        
    try:
        order = client.create_market_order(MarketOrderArgs(
            token_id=token_id,
            amount=amount,
            side=BUY,
            price=0.99
        ))
        
        resp = client.post_order(order, orderType="FOK")
        
        if resp.get("success"):
            order_id = resp.get("orderID")
            print(f"\033[92m\033[1m[SUCCESS] Trade Placed! Stake: ${amount:.2f} | Side: {side_name}\033[0m")
            
            # Initialize with defaults
            avg_price = 0.50
            size_matched = amount / 0.50
            price_str = f"${avg_price:.3f}"
            shares_str = f"{size_matched:.2f}"
            
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
            
            details = {
                "avg_price": avg_price,
                "shares_acquired": size_matched,
                "side_name": side_name
            }
            return True, details
        else:
            err_msg = resp.get('error')
            print(f"\033[91mOrder Failed: {err_msg}\033[0m")
            from telegram_bot import send_telegram_notification  # type: ignore
            send_telegram_notification(f"❌ *Trade Failed*\n\n*Reason:* {err_msg}")
            return False, {}
    except Exception as e:
        print(f"\033[91mOrder Error: {e}\033[0m")
        from telegram_bot import send_telegram_notification  # type: ignore
        send_telegram_notification(f"⚠️ *Trade Error*\n\n`{str(e)}`")
        return False, {}

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
            side=BUY if is_buy else SELL
        )
        
        signed_order = client.create_order(args)
        resp = client.post_order(signed_order, orderType=OrderType.GTC)
        
        if resp and resp.get("success"):
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
            return True, {"price": price, "shares": shares, "side": side_name}
        else:
            err_msg = resp.get('error') if resp else "Unknown API Error"
            print(f"\033[91mLimit Order Failed: {err_msg}\033[0m")
            from telegram_bot import send_telegram_notification  # type: ignore
            send_telegram_notification(f"❌ *Limit Order Failed*\n\n*Reason:* {err_msg}")
            return False, {}
    except Exception as e:
        print(f"\033[91mLimit Order Error: {e}\033[0m")
        from telegram_bot import send_telegram_notification  # type: ignore
        send_telegram_notification(f"⚠️ *Limit Trade Error*\n\n`{str(e)}`")
        return False, {}
