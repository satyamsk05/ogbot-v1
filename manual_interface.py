import sys
from risk_manager import validate_bet  # type: ignore
from execution import place_market_order  # type: ignore

def input_thread_func(mc):
    """
    mc is the shared ModeController instance.
    """
    while mc.running:
        try:
            line = sys.stdin.readline()
            if not line:
                break
            line = line.strip().lower()
            if not line:
                continue
                
            parts = line.split()
            cmd = parts[0]
            
            if cmd == "exit":
                mc.running = False
                print("Exiting...")
                break
            elif cmd == "auto":
                success, msg = mc.set_mode("AUTO")
                if not success:
                    print(f"\n[ERROR] {msg}")
                else:
                    print("\n[INFO] Switched to AUTO mode")
            elif cmd == "manual":
                mc.set_mode("MANUAL")
                print("\n[INFO] Switched to MANUAL mode")
            elif cmd == "bet":
                if mc.bot_mode != "MANUAL":
                    print("\n[ERROR] Cannot place manual bet in AUTO mode")
                    continue
                    
                if len(parts) < 4:
                    print("\n[ERROR] Usage: bet <5m|15m> <green|red> <amount>")
                    continue
                    
                tf = parts[1]
                side_input = parts[2]
                try:
                    amount = float(parts[3])
                except ValueError:
                    print("\n[ERROR] Invalid amount")
                    continue
                    
                side = "UP" if side_input == "green" else "DOWN" if side_input == "red" else None
                if not side:
                    print("\n[ERROR] Side must be green or red")
                    continue
                    
                if tf == "5m":
                    data = mc.data_5m
                elif tf == "15m":
                    data = mc.data_15m
                else:
                    print("\n[ERROR] Timeframe must be 5m or 15m")
                    continue
                    
                token_id = data['up_token'] if side == "UP" else data['down_token']
                if not token_id:
                    print("\n[ERROR] Market data not available for this timeframe yet")
                    continue
                    
                is_valid, msg = validate_bet(amount, mc.current_balance)
                if not is_valid:
                    print(f"\n[ERROR] Validation failed: {msg}")
                    continue
                    
                print(f"\n[INFO] Executing manual bet: ${amount} on {tf} {side_input.upper()}...")
                success = place_market_order(mc.client, token_id, amount, side)
                if success:
                    print("[INFO] Manual bet placed successfully!")
                else:
                    print("[ERROR] Manual bet failed!")
                    
            else:
                print(f"\n[ERROR] Unknown command: {cmd}")
                
        except Exception as e:
            print(f"Input thread error: {e}")
