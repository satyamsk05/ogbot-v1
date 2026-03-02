import os
from dotenv import load_dotenv  # type: ignore

load_dotenv()

# Operating Mode: "MANUAL" or "AUTO"
BOT_MODE = os.getenv("BOT_MODE", "MANUAL").upper()
DEFAULT_MARTINGALE_TYPE = os.getenv("DEFAULT_MARTINGALE_TYPE", "LINEAR").upper() # "LINEAR" or "TRIPLE"

# Limits and constraints
MAX_SINGLE_BET = float(os.getenv("MAX_SINGLE_BET", "10.0"))
MIN_WALLET_BALANCE = float(os.getenv("MIN_WALLET_BALANCE", "5.0"))
MAX_PROGRESSION_STEPS = int(os.getenv("MAX_PROGRESSION_STEPS", "6")) # e.g., 6 steps of 3x: 1, 3, 9, 27, 81, 243

# Telegram integration
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
ALLOWED_CHAT_ID = os.getenv("ALLOWED_CHAT_ID", "").strip()

# Polymarket credentials
PRIVATE_KEY = os.getenv("PRIVATE_KEY", "").strip().lstrip("0x")
SIGNATURE_TYPE = int(os.getenv("SIGNATURE_TYPE", "1"))
POLY_FUNDER = os.getenv("POLY_FUNDER", "").strip()

# API Endpoints
HOST = "https://clob.polymarket.com"
GAMMA_API = "https://gamma-api.polymarket.com"
SYMBOL = "BTCUSDT"

# Dry run flag for testing
DRY_RUN = os.getenv("DRY_RUN", "False").lower() in ("true", "1", "yes", "t")
VIRTUAL_START_BALANCE = float(os.getenv("VIRTUAL_START_BALANCE", "500.0"))
