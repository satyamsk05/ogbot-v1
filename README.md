# 🤖 OGBot v1+ — Polymarket BTC Trading Bot

OGBot is a sophisticated, dual-mode trading bot designed for Polymarket's BTC Up/Down markets. It combines real-time data from Binance with Polymarket's CLOB API to execute automated and manual trades based on a proven Martingale reversal strategy.

---

## 🚀 Key Features

- **Dual-Mode Operation:** Toggle between `MANUAL` and `AUTO` trading modes.
- **Automated Reversal Strategy:** Monitors 5-minute and 15-minute BTC trends. Executes trades on 3-candle reversal patterns.
- **Martingale Betting Systems:** Supports **Linear** (Safe) and **Triple** (High Profit) progression systems.
- **Real-Time Dashboards:**
  - **Terminal UI:** Premium Rich-based dashboard for desktop monitoring.
  - **Telegram Bot:** Fully interactive Telegram menu for remote control and instant notifications.
- **Dry Run Mode:** Risk-free simulation mode with virtual balance for strategy testing.
- **Auto-Redeem:** Periodically cashes out winning positions automatically.
- **Daily Reports:** Automatically sends a PnL summary at 23:59 daily.

---

## 🏗️ Architecture Overview

OGBot is built on a multi-threaded architecture to ensure real-time responsiveness:

- **Thread 1:** Binance BTC live price tracker (0.1s interval).
- **Thread 2/3:** Polymarket market data & candle loaders (5s interval).
- **Thread 4:** Interactive Terminal CLI.
- **Thread 5:** Telegram Bot polling and UI manager.
- **Thread 6:** Daily summary scheduler.
- **Main Thread:** Orchestrates strategy cycles and auto-redemption.

---

## 🛠️ Installation & Setup

### 1. Prerequisite
- Python 3.10+
- A Polygon wallet with USDC (if not using `DRY_RUN`)
- Telegram Bot Token (from [@BotFather](https://t.me/BotFather))

### 2. Clone the Repository
```bash
git clone https://github.com/satyamsk05/ogbot-v1.git
cd ogbot-v1
```

### 3. Setup Virtual Environment
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 4. Configuration
Create a `.env` file from the example:
```bash
cp .env.example .env
```

Edit `.env` with your credentials:
```env
PRIVATE_KEY=your_polygon_private_key
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
ALLOWED_CHAT_ID=your_telegram_chat_id
DRY_RUN=true
VIRTUAL_START_BALANCE=500
```

---

## 🕹️ Usage

### Running the Bot
```bash
python3 main.py
```

### Telegram Commands
| Command | Action |
|---------|--------|
| `/start` | Open the main menu dashboard |
| `/history` | View the last 20 trades |
| `/cashout` | Manually redeem all winning positions |
| `/settings` | Update base bet and martingale type |

---

## 🛡️ Betting Systems

| Step | Linear (Safe) | Triple (Max Profit) |
|------|---------------|---------------------|
| 1    | $2.0          | $2.0                |
| 2    | $4.0          | $6.0                |
| 3    | $6.0          | $18.0               |
| 4    | $8.0          | $54.0               |
| 5    | $10.0         | $162.0              |

---

## 📂 Project Structure

- `main.py`: Entry point and thread manager.
- `mode_controller.py`: Core logic orchestration.
- `strategy_5m.py` / `strategy_15m.py`: Timeframe-specific betting logic.
- `execution.py`: Integration with Polymarket CLOB.
- `telegram_bot.py`: Telegram interface and notifications.
- `dashboard.py`: Terminal UI implementation.

---

## ⚖️ Disclaimer
This bot is for educational purposes only. Trading involves significant risk. Always test in **DRY_RUN** mode before using real funds.
