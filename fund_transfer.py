import os
import config # type: ignore
from web3 import Web3 # type: ignore
from web3.middleware import ExtraDataToPOAMiddleware # type: ignore

# Known USDC contract addresses on Polygon
USDC_CONTRACTS = {
    "Bridged USDC (USDC.e)": "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174",
    "Native USDC (USDC)": "0x3c499c542cEF5E3811e1192ce70d8cC03d5c3359"
}

# Standard ERC20 ABI (Transfer & BalanceOf only)
ERC20_ABI = [
    {
        "constant": False,
        "inputs": [
            {"name": "_to", "type": "address"},
            {"name": "_value", "type": "uint256"}
        ],
        "name": "transfer",
        "outputs": [{"name": "", "type": "bool"}],
        "type": "function"
    },
    {
        "constant": True,
        "inputs": [{"name": "_owner", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"name": "balance", "type": "uint256"}],
        "type": "function"
    }
]

def transfer_usdc(to_address: str, amount_usd: float) -> tuple[bool, str]:
    """
    Transfers USDC tokens on Polygon to another wallet.
    Returns (Success, message/txHash)
    """
    if not config.PRIVATE_KEY:
        return False, "PRIVATE_KEY not found in config."
        
    rpc_url = os.getenv("RPC_URL", "https://polygon-rpc.com")
    
    w3 = Web3(Web3.HTTPProvider(rpc_url))
    w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
    
    if not w3.is_connected():
        return False, "Failed to connect to Polygon network."
        
    if not w3.is_address(to_address):
        return False, f"Invalid destination address: {to_address}"
        
    to_address_checksum = w3.to_checksum_address(to_address)
        
    try:
        account = w3.eth.account.from_key(config.PRIVATE_KEY)
        from_address = account.address
        
        # We'll check all known USDC contracts
        best_contract_addr = None
        max_balance = -1.0
        
        for name, addr in USDC_CONTRACTS.items():
            checksum_addr = w3.to_checksum_address(addr)
            contract = w3.eth.contract(address=checksum_addr, abi=ERC20_ABI)
            balance_wei = contract.functions.balanceOf(from_address).call()
            balance_usd = balance_wei / 1e6
            
            if balance_usd > max_balance:
                max_balance = balance_usd
                best_contract_addr = checksum_addr
                
        if max_balance < amount_usd:
            return False, f"Insufficient balance. You have ${max_balance:.2f} max. (Check if funds are in a Proxy Wallet or Polymarket Clob)"
            
        usdc_contract = w3.eth.contract(address=best_contract_addr, abi=ERC20_ABI)
        
        # Amount in 6 decimals
        amount_wei = int(amount_usd * 1e6)
        
        # Build Tx
        nonce = w3.eth.get_transaction_count(from_address)
        gas_price = w3.eth.gas_price
        
        tx = usdc_contract.functions.transfer(to_address_checksum, amount_wei).build_transaction({
            'chainId': 137, # Polygon mainnet
            'gas': 100000,   # Standard ERC20 transfer limit
            'gasPrice': int(gas_price * 1.1),
            'nonce': nonce,
        })
        
        signed_tx = w3.eth.account.sign_transaction(tx, private_key=config.PRIVATE_KEY)
        tx_hash = w3.eth.send_raw_transaction(signed_tx.rawTransaction)
        
        return True, w3.to_hex(tx_hash)
        
    except Exception as e:
        return False, str(e)
