import config  # type: ignore

def validate_bet(amount, current_balance):
    """
    Validates if a bet is safe to place based on configuration rules.
    Returns (True, "OK") if safe, otherwise (False, reason_string).
    """
    if amount > config.MAX_SINGLE_BET:
        return False, f"Amount ${amount:.2f} exceeds MAX_SINGLE_BET (${config.MAX_SINGLE_BET:.2f})"
        
    if current_balance < config.MIN_WALLET_BALANCE:
        return False, f"Balance ${current_balance:.2f} is below MIN_WALLET_BALANCE (${config.MIN_WALLET_BALANCE:.2f})"
        
    if amount > current_balance:
        return False, "Insufficient balance"
        
    return True, "OK"
