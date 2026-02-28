"""
Utility functions used across the application.
"""
import logging
from decimal import Decimal
from typing import Any
from django.conf import settings

logger = logging.getLogger(__name__)

def normalize_amount(amount: Any) -> Decimal:
    """
    Normalize an amount to a Decimal with the correct precision.
    
    Args:
        amount: The amount to normalize (can be int, float, str, or Decimal)
    
    Returns:
        Decimal: Normalized amount
    
    Raises:
        ValueError: If amount is invalid
    """
    try:
        decimal_amount = Decimal(str(amount))
        
        # Ensure positives
        if decimal_amount <= 0:
            raise ValueError("Amount must be positive")
        
        # Quantize to the correct decimal places
        quantize_value = Decimal(10) ** -settings.WALLET_DECIMAL_PLACES
        return decimal_amount.quantize(quantize_value)
    except (ValueError, TypeError, ArithmeticError) as e:
        logger.error(f"Failed to normalize amount {amount}: {e}")
        raise ValueError(f"Invalid amount: {amount}")
    
def generate_reference(prefix: str = "TXN") -> str:
    """
    Generate a unique reference for a transaction.
    
    Args:
        prefix: Prefix for the reference
    
    Returns:
        str: Unique reference
    """
    
    import uuid 
    from datetime import datetime
    
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    unique_id = str(uuid.uuid4())[:8].upper()
    
    return f"{prefix} - {timestamp} - {unique_id}"
   