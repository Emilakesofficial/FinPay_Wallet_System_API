"""
Custom exceptions for the wallet system.
"""
from rest_framework.views import exception_handler
from rest_framework.response import Response
from rest_framework import status

class WalletException(Exception):
    """Base exception for wallet-related errors."""
    default_message = "A wallet error occurred"
    status_code = status.HTTP_400_BAD_REQUEST
    
    def __init__(self, message=None, **kwargs):
        self.message = message or self.default_message
        self.extra = kwargs
        super().__init__(self.message)
        
class InsufficientFundsException(WalletException):
    """Raised when a wallet doesn't have enough balance for an operation."""
    default_message = "Insufficient funds"
    status_code = status.HTTP_400_BAD_REQUEST
    
class InvalidAmountException(WalletException):
    """Raised when an invalid amount is provided."""
    default_message = "Invalid amount"
    status_code = status.HTTP_400_BAD_REQUEST
    
class WalletNotFoundException(WalletException):
    """Raised when a wallet is not found."""
    default_message = "Wallet not found"
    status_code = status.HTTP_404_NOT_FOUND
    
class TransactionNotFoundException(WalletException):
    """Raised when a transaction is not found."""
    default_message = "Transaction not found"
    status_code = status.HTTP_404_NOT_FOUND


class DuplicateTransactionException(WalletException):
    """Raised when a duplicate idempotency key is detected."""
    default_message = "Duplicate transaction"
    status_code = status.HTTP_409_CONFLICT
    
class ReconciliationException(WalletException):
    """Raised when reconciliation detects discrepancies."""
    default_message = "Reconciliation failed"
    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR

def custom_exception_handler(exc, context):
    """
    Custom exception handler that formats wallet exceptions consistently.
    """
    # Call REST framework's default exception handler first
    response = exception_handler(exc, context)
    
    # Handle our custom exceptions
    if isinstance(exc, WalletException):
        return Response(
            {
                'error': exc.__class__.__name__,
                'message': exc.message,
                'details': exc.extra
            },
            status=exc.status_code
        )
    
    return response