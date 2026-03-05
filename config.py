import os
from dotenv import load_dotenv  # type: ignore
from web3 import Web3
from web3.middleware import ExtraDataToPOAMiddleware # type: ignore

load_dotenv()

# Operating Mode: "MANUAL" or "AUTO"
BOT_MODE = os.getenv("BOT_MODE", "MANUAL").upper()
DEFAULT_MARTINGALE_TYPE = "TRIPLE"  # Only TRIPLE (3x) is supported

# Limits and constraints
MAX_SINGLE_BET = float(os.getenv("MAX_SINGLE_BET", "10.0"))
MIN_WALLET_BALANCE = float(os.getenv("MIN_WALLET_BALANCE", "5.0"))
MAX_PROGRESSION_STEPS = int(os.getenv("MAX_PROGRESSION_STEPS", "6"))

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

# ✅ FIX: DRY_RUN aur VIRTUAL_START_BALANCE add kiya
DRY_RUN = os.getenv("DRY_RUN", "true").lower() == "true"
VIRTUAL_START_BALANCE = float(os.getenv("VIRTUAL_START_BALANCE", "500.0"))

# Server/Deployment Options
HEADLESS = os.getenv("HEADLESS", "false").lower() == "true"
LOG_FILE = "bot.log"

from zoneinfo import ZoneInfo
ET_TZ = ZoneInfo("America/New_York")

# RPC & Web3 Settings
POLYGON_RPCS = [
    "https://polygon-rpc.com",
    "https://rpc-mainnet.maticvigil.com",
    "https://rpc.ankr.com/polygon",
    "https://1rpc.io/matic"
]

def get_w3():
    """Returns a connected Web3 instance using fallback RPCs."""
    
    # Try custom RPC from env first
    env_rpc = os.getenv("RPC_URL")
    rpcs = [env_rpc] + POLYGON_RPCS if env_rpc else POLYGON_RPCS
    
    for url in rpcs:
        try:
            w3 = Web3(Web3.HTTPProvider(url, request_kwargs={'timeout': 10}))
            if w3.is_connected():
                w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
                return w3
        except Exception:
            continue
    return None