import telebot  # type: ignore
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton  # type: ignore
import config  # type: ignore
import threading
import time
from datetime import datetime

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
        mode_label = "🟢 AUTO" if mc.bot_mode == "AUTO" else "🔴 MANUAL"
        return (
            f"🚀 *POLYSYNC PREMIUM DASHBOARD*\n"
            f"──────────────────\n"
            f"👤 *Mode:* `{mode_label}`\n"
            f"💰 *Balance:* `${mc.current_balance:,.2f}`\n"
            f"📊 *BTC Price:* `${mc.live_price:,.2f}`\n"
            f"📅 *Daily PnL:* `${mc.daily_pnl:,.2f}`\n"
            f"🕒 *Last Update:* `{now}`\n"
            f"──────────────────\n"
        )

    def main_menu_markup():
        markup = InlineKeyboardMarkup(row_width=2)
        markup.add(
            InlineKeyboardButton("📈 Trade 5m", callback_data="nav_trade_5m"),
            InlineKeyboardButton("📉 Trade 15m", callback_data="nav_trade_15m"),
            InlineKeyboardButton("⚙️ Settings", callback_data="nav_settings"),
            InlineKeyboardButton("💸 Transfer", callback_data="nav_transfer"),
            InlineKeyboardButton("🔄 Refresh", callback_data="nav_home")
        )
        return markup

    def trade_menu_markup(timeframe):
        markup = InlineKeyboardMarkup(row_width=2)
        markup.add(
            InlineKeyboardButton("🟩 BUY UP ($1)", callback_data=f"bet_buy_{timeframe}_green_1"),
            InlineKeyboardButton(" SELL UP", callback_data=f"bet_sell_{timeframe}_green_1"),
            InlineKeyboardButton(" BUY DOWN ($1)", callback_data=f"bet_buy_{timeframe}_red_1"),
            InlineKeyboardButton(" SELL DOWN", callback_data=f"bet_sell_{timeframe}_red_1"),
            InlineKeyboardButton("🎯 Custom Limit", callback_data=f"nav_limit_{timeframe}"),
            InlineKeyboardButton("⬅️ Back", callback_data="nav_home")
        )
        return markup

    def settings_menu_markup():
        markup = InlineKeyboardMarkup(row_width=2)
        mode_btn_text = "🔄 Set AUTO Mode" if mc.bot_mode == "MANUAL" else "🔄 Set MANUAL Mode"
        markup.add(
            InlineKeyboardButton(mode_btn_text, callback_data="toggle_mode"),
            InlineKeyboardButton("📊 Detailed Status", callback_data="nav_status"),
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
            elif page == "status":
                status_text = (
                    f"{get_header()}\n"
                    f"🔍 *Detailed Status:*\n"
                    f"• Auto Strategy: `Active`\n"
                    f"• 5m Sequence: `{mc.data_5m.get('sequence', 'N/A')}`\n"
                    f"• 15m Sequence: `{mc.data_15m.get('sequence', 'N/A')}`\n"
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

    # --- Settings Logic ---
    @bot.callback_query_handler(func=lambda call: call.data == "toggle_mode")
    def toggle_mode_handler(call):
        if not is_allowed(call.message): return
        new_mode = "AUTO" if mc.bot_mode == "MANUAL" else "MANUAL"
        success, msg = mc.switch_mode(new_mode)
        bot.answer_callback_query(call.id, msg)
        # Update settings screen
        nav_handler(type('obj', (object,), {'data': 'nav_settings', 'message': call.message, 'id': call.id}))

    # --- Trade Execution Logic ---
    @bot.callback_query_handler(func=lambda call: call.data.startswith('bet_'))
    def bet_handler(call):
        if not is_allowed(call.message): return
        
        if mc.bot_mode != "MANUAL":
            bot.answer_callback_query(call.id, "❌ Error: Switch to MANUAL mode first!", show_alert=True)
            return

        bot.answer_callback_query(call.id, "⚡ Processing Trade...")
        parts = call.data.split('_') # bet_buy_5m_green_1
        action, timeframe, side, amount = parts[1], parts[2], parts[3], float(parts[4])
        
        execute_trade_logic(call.message.chat.id, action, timeframe, side, amount)

    def execute_trade_logic(chat_id, action, timeframe, side, amount):
        from risk_manager import validate_bet
        from execution import place_market_order, place_limit_order

        if action == "buy":
            is_valid, reason = validate_bet(amount, mc.current_balance)
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
            success = place_market_order(mc.client, token_id, amount, signal)
        else:
            success = place_limit_order(mc.client, token_id, amount, 0.01, signal, is_buy=False)
            
        if success:
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
            from execution import place_limit_order
            target_data = mc.data_5m if tf == "5m" else mc.data_15m
            token_id = target_data.get('up_token') if coin == "up" else target_data.get('down_token')
            is_buy = True if action == "buy" else False
            bot.send_message(message.chat.id, "⏳ *Placing Limit Order...*", parse_mode="Markdown")
            place_limit_order(mc.client, token_id, amount, price, coin.upper(), is_buy)
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
            import fund_transfer
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
