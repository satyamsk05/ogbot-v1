# 🤖 OGBot v1+ — Full Architecture Diagram

---

## 1. System Overview

![System Architecture](docs/system_architecture.png)

---

## 2. Betting System Architecture

The OGBot v1+ betting engine is a high-precision, state-based system that combines pattern recognition with aggressive recovery logic.

### 📊 Strategy Flowchart

```mermaid
graph TD
    A[Start Cycle] --> B{Active Bet?}
    B -- Yes --> C{Round Expired + Delay?}
    C -- Yes --> D[Resolve Bet vs Target Price]
    D --> E{WIN?}
    E -- Yes --> F[Reset Martingale Step 0]
    E -- No --> G[Inc Martingale Step + Set Force]
    
    B -- No --> H{Force Next Bet?}
    H -- Yes --> I[Place Next Martingale Step Bet]
    H -- No --> J{3-Candle Signal?}
    J -- Yes --> K[Place Step 1 Bet]
    J -- No --> L[Wait for Next Cycle]
    
    F --> L
    G --> L
    I --> L
    K --> L
```

---

---

## 3. Martingale Betting Progression

The bot uses a **Fixed Recovery Sequence** to ensure losses are recovered and profit is secured within 6 steps.

| Step | Amount | Recovery Logic |
|---|---|---|
| Step 1 | $2.00 | Base Entry (Reversal) |
| Step 2 | $5.00 | Immediate Follow-up |
| Step 3 | $10.00 | Immediate Follow-up |
| Step 4 | $22.00 | Immediate Follow-up |
| Step 5 | $45.00 | Immediate Follow-up |
| Step 6 | $95.00 | Final Recovery |
| **WIN** | Reset | Back to Step 1 ✅ |
| **LOSS** | Next | Continue to Next Step ❌ |

---

---

## 4. Thread Architecture

| Thread | Function | Interval | What it Does |
|--------|----------|----------|-------------|
| Thread 1 | `fetch_live_price()` | 0.1s | Binance BTC live price |
| Thread 2 | `fetch_market_data("5m")` | 5s | 5m candles + Polymarket tokens |
| Thread 3 | `fetch_market_data("15m")` | 5s | 15m candles + Polymarket tokens |
| Thread 4 | `input_thread_func()` | Blocking | Terminal CLI commands |
| Thread 5 | `run_telegram_bot()` | Polling | Telegram UI & callbacks |
| Thread 6 | `daily_summary_scheduler()`| 30s | Checks for 23:59 summary |
| **Main** | `process_cycle()` | 5s | Strategy processing + Auto redeem |

---

## 5. File Responsibilities

| File | Role | Key Functions |
|------|------|--------------|
| `main.py` | Entry point, thread manager | `fetch_live_price()`, `fetch_market_data()` |
| `mode_controller.py` | Brain — orchestrates everything | `process_cycle()`, `set_mode()`, `toggle_auto_redeem()` |
| `strategy_5m.py` | 5-minute auto-betting logic | `process()`, `get_current_bet_amount()` |
| `strategy_15m.py` | 15-minute auto-betting logic | `process()`, `get_candle_sequence_display()` |
| `execution.py` | Trade engine + cashout | `place_market_order()`, `redeem_all_funds()` |
| `telegram_bot.py` | Telegram UI | `run_telegram_bot()`, `send_telegram_notification()` |
| `dashboard.py` | Terminal Rich UI | `generate_layout()`, market panels |
| `risk_manager.py` | Bet validation | `validate_bet()` |
| `fund_transfer.py` | USDC transfers | `transfer_usdc()` |
| `config.py` | Settings loader | Reads `.env` |

---

## 6. Data Flow

```
Binance API ──(candles)──► main.py ──► ModeController.data_5m/data_15m
                                            │
                                     process_cycle() (every 5s)
                                            │
                              ┌──────────────┴──────────────┐
                              ▼                              ▼
                        Strategy5M                    Strategy15M
                              │                              │
                    Check Warmup (3 candles)       Check Warmup (3 candles)
                    Check Active Bet               Check Active Bet
                    Scan Last 3 Candles            Scan Last 3 Candles
                              │                              │
                    🔴🔴🔴 = Bet GREEN             🟢🟢🟢 = Bet RED
                              │                              │
                              └──────────┬───────────────────┘
                                         ▼
                              execution.place_market_order()
                                         │
                              Polymarket CLOB API (FOK order)
                                         │
                              📱 Telegram Notification
```

---

## 7. Telegram Menu Tree

```
🏠 Home Dashboard
├── ▶️ START / ⏸ STOP Bot
├── 🛡️ SAFE Mode (1,2,3)
├── 🚀 HIGH PROFIT (1,3,9)
├── 💰 Cashout Now
├── 🤖 Auto Cash: ON/OFF
├── 📈 Trade 5m
│   ├── 🟩 BUY UP
│   ├── SELL UP
│   ├── BUY DOWN
│   ├── SELL DOWN
│   └── 🎯 Custom Limit
├── 📉 Trade 15m (same as 5m)
├── 💸 Withdraw $
│   ├── Enter Address
│   └── Enter Amount → Send USDC
├── ⚙️ More Settings
│   ├── 💰 Set Base Bet
│   ├── 🕒 Market Mode (5m/15m/Both)
│   ├── 📊 Detailed Status
│   ├── 📝 Trade History
│   ├── 📊 Daily Report
│   └── � Test All Alerts
└── �🔄 Refresh Dashboard
```

---

## 8. Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `PRIVATE_KEY` | ✅ | Polygon wallet private key |
| `TELEGRAM_BOT_TOKEN` | ✅ | Telegram bot API token |
| `ALLOWED_CHAT_ID` | ✅ | Authorized Telegram chat ID |
| `BOT_MODE` | ❌ | Startup mode: `MANUAL` or `AUTO` |
| `DRY_RUN` | ❌ | `True` for simulation mode (default) |
| `VIRTUAL_START_BALANCE` | ❌ | Starting virtual wallet (default: 500) |
| `MAX_SINGLE_BET` | ❌ | Maximum allowed stake (default: 10) |
| `MAX_PROGRESSION_STEPS`| ❌ | Max martingale steps (default: 6) |

---

## 10. Technical Concepts

### 🎯 Target Price Persistence
To prevent "Ghost Losses" caused by market jitter at round starts:
- **Storage:** The `active_bet_target_price` is stored at the exact moment a trade is placed.
- **Comparison:** Resolution is performed by comparing the **Last Closed Candle** price against this **Persistent Target**, NOT the current live price.

### ⚡ Immediate Martingale
- **Signal Independence:** After a loss, the bot enters a "Forced State" (`force_next_bet = True`).
- **Consecutive Entry:** Forcing allows the bot to skip the 3-candle pattern search and place the next bet at the very beginning (0.0s) of the next candle.
- **Profit Seeker:** This maximizes recovery speed by staying on the trend until it flips.

---
