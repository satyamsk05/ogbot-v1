# 🤖 OGBot v1+ | Polymarket BTC Trading Bot
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Platform: Polygon](https://img.shields.io/badge/network-Polygon-purple.svg)](https://polygon.technology/)

> **A high-performance, dual-mode trading bot for Polymarket's BTC Up/Down markets.**

---

## 💎 Overview
OGBot v1+ is a professional-grade trading engine designed to exploit short-term volatility in Polymarket's Bitcoin binary options. It features a robust multi-threaded architecture, real-time market synchronization, and a premium visual experience for both desktop and mobile users.

---

## 🚀 Key Features

### 🧠 Intelligent Trading
- **Automated Reversal Strategy:** Monitors 5m & 15m timeframes. Triggers on 3-candle reversal patterns.
- **Custom Martingale Progression:** [2, 5, 10, 22, 45, 95] sequence for optimized recovery.
- **Auto-Redeem:** Systematic profit-taking for closed winning positions.

### 📱 Premium Interfaces
- **Interactive Telegram UI:** Full mobile control via Persistent Menus and Inline Grid layouts.
- **Rich Desktop Dashboard:** Detailed terminal HUD for real-time monitoring.
- **Real-Time Price Sync:** 0.1s Binance price tracking for maximum precision.

### 🛡️ Reliability & Security
- **Server Readiness:** Headless mode & file-based logging for 24/7 VPS deployment.
- **Dry-Run Mode:** Test strategies with a virtual balance without risking real USDC.
- **Access Control:** Restricted Telegram chat IDs to ensure only you control the bot.

---

## 🏗 Architecture
The system is built for resilience and speed, utilizing a modular design and multi-threaded execution.

### System Components
| Layer | Description |
| :--- | :--- |
| **Brain** | `ModeController` orchestrates logic, data, and strategy states. |
| **Execution** | `execution.py` handles orders and redemption via CLOB API. |
| **Strategy** | `strategy_5m.py` / `strategy_15m.py` manage specific timeframe patterns. |
| **UI/UX** | `telegram_bot.py` and `dashboard.py` provide visual feedback. |

### Visual Documentation
- [System Architecture](docs/system_architecture.png)
- [Strategy Flowchart](docs/strategy_flowchart.png)

---

## 🛠 Setup & Installation

### 1. Requirements
- Python **3.10+**
- Polygon Wallet (Private Key)
- Telegram Bot API Token

### 2. Fast Installation
```bash
# Clone and enter
git clone https://github.com/satyamsk05/ogbot-v1.git
cd ogbot-v1

# Setup environment
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 3. Configuration
Copy `.env.example` to `.env` and fill in your credentials:
```env
PRIVATE_KEY=your_private_key
TELEGRAM_BOT_TOKEN=your_bot_token
ALLOWED_CHAT_ID=your_telegram_id
DRY_RUN=True
HEADLESS=False
```

---

## 🕹 Usage & Controls

### Starting the Bot
```bash
python3 main.py
```

### Server Deployment
For 24/7 background operation:
```bash
# Set HEADLESS=True in .env
nohup python3 main.py &
```
*Logs are automatically saved to `bot.log`.*

### Telegram Commands
| Action | Detail |
| :--- | :--- |
| **🛢 STATUS** | Detailed performance and win-rate statistics. |
| **💎 WALLET** | Check balance and initiate USDC transfers. |
| **🟢 START BOT** | Switch to fully automated Martingale mode. |
| **⚡ RESET** | Manually reset the Martingale progression to Step 1. |

---

## � Betting Progression
*Triggered after 3 consecutive same-colored candles.*

| Step | Amount | Step | Amount |
| :--- | :--- | :--- | :--- |
| **1** | $2.0 | **4** | $22.0 |
| **2** | $5.0 | **5** | $45.0 |
| **3** | $10.0 | **6** | $95.0 |

---

## ⚖️ Disclaimer
*This bot is for experimental purposes. Binary options trading involves substantial risk. The developer is not responsible for any financial losses incurred.*
