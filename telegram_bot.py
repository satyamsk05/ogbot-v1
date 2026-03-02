import telebot  # type: ignore
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton  # type: ignore
import config  # type: ignore
import threading
import time
from datetime import datetime
import risk_manager
import execution
import fund_transfer

# Simple class for navigation mocking
class NavCall:
    def __init__(self, data, message, call_id):
        self.data = data
        self.message = message
        self.id = call_id

# Global reference for notifications
_bot_instance = None
_alert_chat_id = None

def send_telegram_notification(message_text: str):
    """Called by other modules to push alerts to Telegram"""
    if _bot_instance and _alert_chat_id:
        try:
            _bot_instance.send_message(_alert_chat_id, f"📝 *Notification*\n{message_text}", parse_mode="Markdown")
        except Exception as e:
            print(f"[Telegram] Failed to send notification: {e}")

def run_telegram_bot(mc):
    global _bot_instance, _alert_chat_id
    if not config.TELEGRAM_BOT_TOKEN:
        print("[Telegram] Bot token not provided in .env, skipping Telegram interface.")
        return

    bot = telebot.TeleBot(config.TELEGRAM_BOT_TOKEN)
    _bot_instance = bot
    allowed_chat_id = config.ALLOWED_CHAT_ID
    _alert_chat_id = allowed_chat_id

    def is_allowed(message):
        return str(message.chat.id) == allowed_chat_id if allowed_chat_id else True

    # --- UI Components ---
    def get_header():
        now = datetime.now().strftime("%H:%M:%S")
        
        # Status
        if mc.bot_mode == "AUTO":
            status_line = "⚡ `RUNNING`"
        else:
            status_line = "🔴 `STOPPED`"
        
        cashout_tag = "✅" if mc.auto_redeem_enabled else "❌"
        
        # Live strategy state
        s5 = mc.strategy_5m
        s15 = mc.strategy_15m
        
        seq_5m = s5.get_candle_sequence_display(mc.data_5m.get('candles', []))
        seq_15m = s15.get_candle_sequence_display(mc.data_15m.get('candles', []))
        
        # PnL color
        pnl_val = mc.daily_pnl
        pnl_icon = "🟢" if pnl_val >= 0 else "🔴"
        pnl_sign = "+" if pnl_val >= 0 else ""
        
        # Balance label
        bal_tag = " [SIM]" if config.DRY_RUN else ""
        
        # Total W/L
        total_w = s5.wins + s15.wins
        total_l = s5.losses + s15.losses
        win_rate = (total_w / (total_w + total_l) * 100) if (total_w + total_l) > 0 else 0
        
        # Current step info
        step_5m = s5.martingale_step + 1
        step_15m = s15.martingale_step + 1
        
        header = (
            f"🤖 *OGBot v1+*  •  {status_line}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"💰 *Balance{bal_tag}:* `${mc.current_balance:,.2f}`\n"
            f"{pnl_icon} *PnL:* `{pnl_sign}${pnl_val:,.2f}`  │  🏆 `{win_rate:.0f}%`\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📊 *5m* {seq_5m}\n"
            f"    └ {s5.next_planned_bet}  (Step {step_5m})\n"
            f"📊 *15m* {seq_15m}\n"
            f"    └ {s15.next_planned_bet}  (Step {step_15m})\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"W `{total_w}` │ L `{total_l}` │ 💸 `${s5.base_bet_amount}` │ ⏰ `{now}`\n"
        )
        return header

    def main_menu_markup():
        markup = InlineKeyboardMarkup(row_width=2)
        
        # Toggle Bot
        if mc.bot_mode == "MANUAL":
            markup.row(InlineKeyboardButton("▶️ START BOT", callback_data="set_mode_AUTO"))
        else:
            markup.row(InlineKeyboardButton("⏸ STOP BOT", callback_data="set_mode_MANUAL"))
        
        # Core Actions
        markup.row(
            InlineKeyboardButton("💰 Cashout Now", callback_data="manual_cashout"),
            InlineKeyboardButton(f"🤖 Auto Cash: {'ON' if mc.auto_redeem_enabled else 'OFF'}", callback_data="toggle_auto_cashout")
        )

        # Trading
        markup.row(
            InlineKeyboardButton("📈 Trade 5m", callback_data="nav_trade_5m"),
            InlineKeyboardButton("📉 Trade 15m", callback_data="nav_trade_15m")
        )
        
        # Bottom Row
        markup.row(
            InlineKeyboardButton("💸 Withdraw", callback_data="nav_transfer"),
            InlineKeyboardButton("⚙️ Settings", callback_data="nav_settings")
        )
        
        markup.row(InlineKeyboardButton("🔄 Refresh", callback_data="nav_home"))
        return markup

    def trade_menu_markup(timeframe):
        markup = InlineKeyboardMarkup(row_width=2)
        strat = mc.strategy_5m if timeframe == "5m" else mc.strategy_15m
        base_amt = strat.base_bet_amount
        target_data = mc.data_5m if timeframe == "5m" else mc.data_15m
        expiry = target_data.get('expiry', '--:--')
        
        markup.row(InlineKeyboardButton(f"🕒 Market Expiry: {expiry}", callback_data="none"))
        markup.add(
            InlineKeyboardButton(f"🟩 BUY UP (${base_amt})", callback_data=f"ask_buy_{timeframe}_green_{base_amt}"),
            InlineKeyboardButton(" SELL UP", callback_data=f"ask_sell_{timeframe}_green_{base_amt}"),
            InlineKeyboardButton(f" BUY DOWN (${base_amt})", callback_data=f"ask_buy_{timeframe}_red_{base_amt}"),
            InlineKeyboardButton(" SELL DOWN", callback_data=f"ask_sell_{timeframe}_red_{base_amt}"),
            InlineKeyboardButton("🎯 Custom Limit", callback_data=f"nav_limit_{timeframe}"),
            InlineKeyboardButton("⬅️ Back", callback_data="nav_home")
        )
        return markup

    def settings_menu_markup():
        markup = InlineKeyboardMarkup(row_width=2)
        markup.add(
            InlineKeyboardButton("💰 Set Base Bet", callback_data="set_base_bet"),
            InlineKeyboardButton("🕒 Market Mode", callback_data="nav_market_mode"),
            InlineKeyboardButton("📊 Detailed Status", callback_data="nav_status")
        )
        if config.DRY_RUN:
            markup.add(
                InlineKeyboardButton("🔄 Reset Wallet", callback_data="reset_virtual"),
                InlineKeyboardButton("⚙️ Sim Settings", callback_data="nav_sim_settings")
            )
            
        markup.add(InlineKeyboardButton("⬅️ Back", callback_data="nav_home"))
        return markup
    
    def market_mode_markup():
        markup = InlineKeyboardMarkup(row_width=1)
        markup.add(
            InlineKeyboardButton("5m ONLY", callback_data="switch_market_5M"),
            InlineKeyboardButton("15m ONLY", callback_data="switch_market_15M"),
            InlineKeyboardButton("BOTH (5m & 15m)", callback_data="switch_market_BOTH"),
            InlineKeyboardButton("⬅️ Back", callback_data="nav_home")
        )
        return markup

    # --- Command Handlers ---
    @bot.message_handler(commands=['start', 'menu', 'home'])
    def send_welcome(message):
        if not is_allowed(message): return
        bot.send_message(message.chat.id, get_header() + "\n🎯 *Main Menu:*", 
                         reply_markup=main_menu_markup(), parse_mode="Markdown")

    # --- Navigation Persistence (Edit instead of send) ---
    @bot.callback_query_handler(func=lambda call: call.data.startswith('nav_'))
    def nav_handler(call):
        if not is_allowed(call.message): return
        page = call.data.replace("nav_", "")
        
        try:
            if page == "home":
                bot.edit_message_text(get_header() + "\n🎯 *Main Menu:*", 
                                     chat_id=call.message.chat.id, message_id=call.message.message_id,
                                     reply_markup=main_menu_markup(), parse_mode="Markdown")
            elif page == "trade_5m":
                bot.edit_message_text(get_header() + "\n📈 *5-Minute Market Controls:*", 
                                     chat_id=call.message.chat.id, message_id=call.message.message_id,
                                     reply_markup=trade_menu_markup("5m"), parse_mode="Markdown")
            elif page == "trade_15m":
                bot.edit_message_text(get_header() + "\n📉 *15-Minute Market Controls:*", 
                                     chat_id=call.message.chat.id, message_id=call.message.message_id,
                                     reply_markup=trade_menu_markup("15m"), parse_mode="Markdown")
            elif page == "settings":
                bot.edit_message_text(get_header() + "\n⚙️ *Bot Settings:*", 
                                     chat_id=call.message.chat.id, message_id=call.message.message_id,
                                     reply_markup=settings_menu_markup(), parse_mode="Markdown")
            elif page == "market_mode":
                bot.edit_message_text(get_header() + "\n🕒 *Choose Market Tracking:*", 
                                     chat_id=call.message.chat.id, message_id=call.message.message_id,
                                     reply_markup=market_mode_markup(), parse_mode="Markdown")
            elif page == "sim_settings":
                markup = InlineKeyboardMarkup(row_width=1)
                markup.add(
                    InlineKeyboardButton(f"💸 Fees: {mc.sim_fees*100:.1f}%", callback_data="set_sim_fees"),
                    InlineKeyboardButton(f"📉 Slippage: {mc.sim_slippage*100:.1f}%", callback_data="set_sim_slippage"),
                    InlineKeyboardButton("💰 Set Custom Balance", callback_data="set_sim_bal"),
                    InlineKeyboardButton("⬅️ Back", callback_data="nav_settings")
                )
                bot.edit_message_text(f"⚙️ *Simulation Settings*\n\nFees and slippage make the dry-run more realistic by simulating market impact and costs.", 
                                     chat_id=call.message.chat.id, message_id=call.message.message_id,
                                     reply_markup=markup, parse_mode="Markdown")
            elif page == "status":
                s5 = mc.strategy_5m
                s15 = mc.strategy_15m
                pnl_color = "🟢" if mc.daily_pnl >= 0 else "🔴"
    
                bal_label = "VIRTUAL WALLET" if config.DRY_RUN else "REAL WALLET"
    
                status_text = (
                    f"📊 *DETAILED STATUS ({bal_label})*\n"
                    f"━━━━━━━━━━━━━━━━━━━━\n"
                    f"💰 *Balance:* `${mc.current_balance:,.2f}`\n"
                    f"📈 *Daily PnL:* {pnl_color} `${mc.daily_pnl:,.2f}`\n"
                    f"──────────────────\n"
                    f"• Betting: `{mc.martingale_type}`\n"
                    f"• 5m Wins/Losses: `{s5.wins}/{s5.losses}`\n"
                    f"• 15m Wins/Losses: `{s15.wins}/{s15.losses}`\n"
                    f"• 5m Step: `{s5.martingale_step + 1}` ({s5.next_planned_bet})\n"
                    f"• 15m Step: `{s15.martingale_step + 1}` ({s15.next_planned_bet})\n"
                    f"• 5m Warmed Up: `{'✅' if s5.is_warmed_up else '❌'}`\n"
                    f"• 15m Warmed Up: `{'✅' if s15.is_warmed_up else '❌'}`\n\n"
                    f"📈 *Simulation Performance:*\n"
                    f"• Win Rate: `{((mc.sim_wins/mc.sim_trades)*100 if mc.sim_trades>0 else 0):.1f}%`\n"
                    f"• Total Stakes: `${mc.sim_stake:,.2f}`\n"
                    f"• Net Goal: `$500 ➔ ${mc.current_balance:,.2f}`\n"
                    f"• Network: `Polygon Mainnet`"
                )
                markup = InlineKeyboardMarkup()
                markup.add(InlineKeyboardButton("⬅️ Back", callback_data="nav_settings"))
                bot.edit_message_text(status_text, chat_id=call.message.chat.id, message_id=call.message.message_id,
                                     reply_markup=markup, parse_mode="Markdown")
            elif page.startswith("limit_"):
                tf = page.split("_")[1]
                start_limit_flow(call.message, tf)
            elif page == "transfer":
                start_transfer_flow(call.message)
        except Exception as e:
            bot.answer_callback_query(call.id, "Error in navigation")
            print(f"Nav error: {e}")

    @bot.callback_query_handler(func=lambda call: call.data == "reset_virtual")
    def reset_virtual_handler(call):
        if not is_allowed(call.message): return
        success, msg = mc.reset_virtual_balance()
        bot.answer_callback_query(call.id, msg, show_alert=True)
        nav_handler(NavCall('nav_home', call.message, call.id))

    @bot.callback_query_handler(func=lambda call: call.data == "set_sim_bal")
    def set_sim_bal_handler(call):
        msg = bot.edit_message_text("💰 *Set Custom Virtual Balance*\nEnter amount (e.g. `1000.0`):", 
                                   chat_id=call.message.chat.id, message_id=call.message.message_id, parse_mode="Markdown")
        bot.register_next_step_handler(msg, sim_bal_input)

    def sim_bal_input(message):
        success, msg = mc.set_virtual_balance(message.text)
        bot.send_message(message.chat.id, f"{'✅' if success else '❌'} {msg}")

    @bot.callback_query_handler(func=lambda call: call.data == "set_sim_fees")
    def set_sim_fees_handler(call):
        msg = bot.edit_message_text("💸 *Set Simulated Fee (%)*\nEnter percentage (e.g. `0.1` for 0.1%):", 
                                   chat_id=call.message.chat.id, message_id=call.message.message_id, parse_mode="Markdown")
        bot.register_next_step_handler(msg, sim_fees_input)

    def sim_fees_input(message):
        try:
            val = float(message.text) / 100.0
            mc.sim_fees = val
            bot.send_message(message.chat.id, f"✅ Fees set to {val*100:.1f}%")
        except:
            bot.send_message(message.chat.id, "❌ Invalid input.")

    @bot.callback_query_handler(func=lambda call: call.data == "set_sim_slippage")
    def set_sim_slippage_handler(call):
        msg = bot.edit_message_text("📉 *Set Simulated Slippage (%)*\nEnter percentage (e.g. `0.5` for 0.5%):", 
                                   chat_id=call.message.chat.id, message_id=call.message.message_id, parse_mode="Markdown")
        bot.register_next_step_handler(msg, sim_slippage_input)

    def sim_slippage_input(message):
        try:
            val = float(message.text) / 100.0
            mc.sim_slippage = val
            bot.send_message(message.chat.id, f"✅ Slippage set to {val*100:.1f}%")
        except:
            bot.send_message(message.chat.id, "❌ Invalid input.")

    # --- Settings Logic ---
    @bot.callback_query_handler(func=lambda call: call.data.startswith('set_mode_'))
    def set_mode_handler(call):
        if not is_allowed(call.message): return
        target_mode = call.data.replace("set_mode_", "")
        success, msg = mc.set_mode(target_mode)
        bot.answer_callback_query(call.id, msg, show_alert=True)
        # Return to home to show updated status/buttons
        nav_handler(NavCall('nav_home', call.message, call.id))

    @bot.callback_query_handler(func=lambda call: call.data.startswith('switch_market_'))
    def switch_market_handler(call):
        if not is_allowed(call.message): return
        mode = call.data.replace("switch_market_", "")
        success, msg = mc.set_strategies_mode(mode)
        bot.answer_callback_query(call.id, msg, show_alert=True)
        nav_handler(NavCall('nav_market_mode', call.message, call.id))

    @bot.callback_query_handler(func=lambda call: call.data == "manual_cashout")
    def manual_cashout_handler(call):
        if not is_allowed(call.message): return
        bot.answer_callback_query(call.id, "⏳ Scanning for winning positions to cash out...")
        # Trigger redemption
        success = execution.redeem_all_funds(mc.client)
        if success:
            bot.answer_callback_query(call.id, "✅ Cashout scan complete!", show_alert=True)
        else:
            bot.answer_callback_query(call.id, "❌ Cashout failed. Check terminal.", show_alert=True)
        nav_handler(NavCall('nav_home', call.message, call.id))

    @bot.callback_query_handler(func=lambda call: call.data == "toggle_auto_cashout")
    def toggle_auto_cashout_handler(call):
        if not is_allowed(call.message): return
        success, msg = mc.toggle_auto_redeem()
        bot.answer_callback_query(call.id, msg, show_alert=True)
        nav_handler(NavCall('nav_home', call.message, call.id))


    @bot.callback_query_handler(func=lambda call: call.data == "set_base_bet")
    def set_base_bet_handler(call):
        msg = bot.edit_message_text("💰 *Set Base Bet Amount*\n\nReply with amount (e.g. `2.0`):", 
                                   chat_id=call.message.chat.id, message_id=call.message.message_id, parse_mode="Markdown")
        bot.register_next_step_handler(msg, base_bet_input)

    def base_bet_input(message):
        success, msg = mc.set_base_bet(message.text)
        bot.send_message(message.chat.id, f"{'✅' if success else '❌'} {msg}")

    # --- Trade Execution Logic ---
    @bot.callback_query_handler(func=lambda call: call.data.startswith('ask_'))
    def ask_confirm_handler(call):
        if not is_allowed(call.message): return
        if mc.bot_mode != "MANUAL":
            bot.answer_callback_query(call.id, "❌ Error: Switch to MANUAL mode first!", show_alert=True)
            return
        
        parts = call.data.split('_') # ask_buy_5m_green_1
        action, timeframe, side, amount = parts[1], parts[2], parts[3], parts[4]
        
        target_data = mc.data_5m if timeframe == "5m" else mc.data_15m
        markup = InlineKeyboardMarkup()
        markup.add(
            InlineKeyboardButton("✅ CONFIRM", callback_data=f"bet_{action}_{timeframe}_{side}_{amount}"),
            InlineKeyboardButton("❌ CANCEL", callback_data=f"nav_trade_{timeframe}")
        )
        
        price_info = target_data.get('beat_price', 0)
        bot.edit_message_text(f"⚠️ *Confirm Manual Trade?*\n\n"
                             f"• Action: `{action.upper()}`\n"
                             f"• Market: `{timeframe}` (Ends: `{target_data.get('expiry')}`)\n"
                             f"• Side: `{side.upper()}`\n"
                             f"• Amount: `${amount}`\n"
                             f"• Approx. Price: `${price_info:.3f}`\n\n"
                             f"⚡ *Note:* High prices (e.g. >0.55) mean the market is already favoring this side.", 
                             chat_id=call.message.chat.id, message_id=call.message.message_id, 
                             reply_markup=markup, parse_mode="Markdown")

    @bot.callback_query_handler(func=lambda call: call.data.startswith('bet_'))
    def bet_handler(call):
        if not is_allowed(call.message): return
        
        bot.answer_callback_query(call.id, "⚡ Trade request received! Processing...")
        parts = call.data.split('_') # bet_buy_5m_green_1
        action, timeframe, side, amount = parts[1], parts[2], parts[3], float(parts[4])
        
        execute_trade_logic(call.message.chat.id, action, timeframe, side, amount)

    def execute_trade_logic(chat_id, action, timeframe, side, amount):
        if action == "buy":
            is_valid, reason = risk_manager.validate_bet(amount, mc.current_balance)
            if not is_valid:
                bot.send_message(chat_id, f"🚨 *Risk Alert:* {reason}", parse_mode="Markdown")
                return

        target_data = mc.data_5m if timeframe == "5m" else mc.data_15m
        signal = "UP" if side == "green" else "DOWN"
        token_id = target_data.get('up_token') if signal == "UP" else target_data.get('down_token')
        
        if not token_id:
            bot.send_message(chat_id, "⚠️ *Error:* Market data not ready.", parse_mode="Markdown")
            return

        status_msg = bot.send_message(chat_id, f"⏳ *Executing {action.upper()}...*\nMarket: `{timeframe}` | Side: `{signal}`", parse_mode="Markdown")
        
        success = False
        if action == "buy":
            success = execution.place_market_order(mc.client, token_id, amount, signal)
        else:
            success = execution.place_limit_order(mc.client, token_id, amount, 0.01, signal, is_buy=False)
            
        if success:
            # Register with strategy for win/loss tracking
            strat = mc.strategy_5m if timeframe == "5m" else mc.strategy_15m
            strat.active_bet_slug = target_data.get('current_slug', '')
            strat.active_bet_side = signal
            
            bot.edit_message_text(f"✅ *{action.upper()} Successful!*\nMarket: `{timeframe}` | Stake: `${amount}`", 
                                 chat_id=chat_id, message_id=status_msg.message_id, parse_mode="Markdown")
        else:
            bot.edit_message_text(f"❌ *{action.upper()} Failed!*", chat_id=chat_id, message_id=status_msg.message_id, parse_mode="Markdown")

    # --- Reusing existing flows but making them cleaner ---
    def start_limit_flow(message, tf):
        markup = InlineKeyboardMarkup()
        markup.add(
            InlineKeyboardButton("🟩 UP (Green)", callback_data=f"lim_coin_{tf}_up"),
            InlineKeyboardButton("🟥 DOWN (Red)", callback_data=f"lim_coin_{tf}_down"),
            InlineKeyboardButton("⬅️ Back", callback_data=f"nav_trade_{tf}")
        )
        bot.edit_message_text(f"Market: {tf}\n\n🪙 *Step 1: Choose Direction*", 
                             chat_id=message.chat.id, message_id=message.message_id, 
                             reply_markup=markup, parse_mode="Markdown")

    @bot.callback_query_handler(func=lambda call: call.data.startswith('lim_coin_'))
    def limit_coin_handler(call):
        parts = call.data.split('_')
        tf, coin = parts[2], parts[3]
        markup = InlineKeyboardMarkup()
        markup.add(
            InlineKeyboardButton("🛒 BUY", callback_data=f"lim_act_{tf}_{coin}_buy"),
            InlineKeyboardButton("💳 SELL", callback_data=f"lim_act_{tf}_{coin}_sell"),
            InlineKeyboardButton("⬅️ Back", callback_data=f"nav_trade_{tf}")
        )
        bot.edit_message_text(f"Market: {tf} | Coin: {coin.upper()}\n\n📊 *Step 2: Choose Action*", 
                             chat_id=call.message.chat.id, message_id=call.message.message_id, 
                             reply_markup=markup, parse_mode="Markdown")

    @bot.callback_query_handler(func=lambda call: call.data.startswith('lim_act_'))
    def limit_action_handler(call):
        parts = call.data.split('_')
        tf, coin, action = parts[2], parts[3], parts[4]
        msg = bot.edit_message_text(
            f"Market: {tf} | Coin: {coin.upper()} | Action: {action.upper()}\n\n"
            f"💵 *Step 3: Enter Limit Price*\n"
            f"Reply with price (e.g. `0.45`):", 
            chat_id=call.message.chat.id, message_id=call.message.message_id, parse_mode="Markdown"
        )
        bot.register_next_step_handler(msg, limit_price_input, tf, coin, action)

    def limit_price_input(message, tf, coin, action):
        try:
            price = float(message.text)
            msg = bot.send_message(message.chat.id, f"🎯 *Price Set:* `${price}`\n\n💰 *Step 4: Enter Stake ($)*\nReply with amount:", parse_mode="Markdown")
            bot.register_next_step_handler(msg, limit_final_exec, tf, coin, action, price)
        except:
            bot.send_message(message.chat.id, "❌ Invalid price. Flow cancelled.")

    def limit_final_exec(message, tf, coin, action, price):
        try:
            amount = float(message.text)
            target_data = mc.data_5m if tf == "5m" else mc.data_15m
            token_id = target_data.get('up_token') if coin == "up" else target_data.get('down_token')
            is_buy = True if action == "buy" else False
            bot.send_message(message.chat.id, "⏳ *Placing Limit Order...*", parse_mode="Markdown")
            execution.place_limit_order(mc.client, token_id, amount, price, coin.upper(), is_buy)
        except:
            bot.send_message(message.chat.id, "❌ Invalid amount. Flow cancelled.")

    # --- Transfer Flow ---
    def start_transfer_flow(message):
        msg = bot.edit_message_text(
            "💸 *Funds Transfer*\n\nReply with the *Target Polygon Address*:",
            chat_id=message.chat.id, message_id=message.message_id, parse_mode="Markdown"
        )
        bot.register_next_step_handler(msg, transfer_addr_input)

    def transfer_addr_input(message):
        addr = message.text.strip()
        if not addr.startswith("0x") or len(addr) != 42:
            bot.send_message(message.chat.id, "❌ Invalid address.")
            return
        msg = bot.send_message(message.chat.id, f"📍 *Target:* `{addr[:10]}...`\n\n💰 *Amount ($):*\nAvailable: `${mc.current_balance:.2f}`", parse_mode="Markdown")
        bot.register_next_step_handler(msg, transfer_final_exec, addr)

    def transfer_final_exec(message, addr):
        try:
            amount = float(message.text)
            bot.send_message(message.chat.id, "⏳ *Processing Transfer...*", parse_mode="Markdown")
            success, res = fund_transfer.transfer_usdc(addr, amount)
            if success:
                bot.send_message(message.chat.id, f"✅ *Sent ${amount}!*\nHash: `{res[:12]}...`", parse_mode="Markdown")
            else:
                bot.send_message(message.chat.id, f"❌ *Failed:* {res}", parse_mode="Markdown")
        except:
            bot.send_message(message.chat.id, "❌ Error.")

    print("[Telegram] Premium UI Active. Listening...")
    bot.infinity_polling()
