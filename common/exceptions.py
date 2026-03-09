"""
Custom exceptions for the wallet system.
"""
import traceback
from django.conf import settings
import structlog
from rest_framework.views import exception_handler
from rest_framework.response import Response
from rest_framework.exceptions import APIException
from rest_framework import status
from django.core.exceptions import ValidationError as DjangoValidationError
from django.http import Http404

logger = structlog.get_logger(__name__)


# ============================================================================
# Base Exception Classes
# ============================================================================

class WalletBaseException(APIException):
    """
    Base exception for all wallet-related errors.
    Provides structured error responses with consistent format.
    """
    status_code = status.HTTP_400_BAD_REQUEST
    default_code = 'error'
    default_message = 'An error occurred'
    
    def __init__(self, message=None, code=None, **extra):
        self.message = message or self.default_message
        self.code = code or self.default_code
        self.extra = extra
        
        # Log the error with context
        logger.error(
            "wallet_error",
            error_type=self.__class__.__name__,
            message=self.message,
            code=self.code,
            **extra
        )
        
        super().__init__(detail=self.message, code=self.code)
    
    def get_full_details(self):
        """Return full error details for API response."""
        return {
            'error': self.__class__.__name__,
            'code': self.code,
            'message': self.message,
            'details': self.extra,
            'status_code': self.status_code
        }

# ============================================================================
# Wallet Exceptions
# ============================================================================

class WalletNotFoundException(WalletBaseException):
    """Raised when a wallet is not found."""
    status_code = status.HTTP_404_NOT_FOUND
    default_code = 'wallet_not_found'
    default_message = 'Wallet not found'

        
class WalletInactiveException(WalletBaseException):
    """Raised when attempting to use an inactive/frozen wallet."""
    status_code = status.HTTP_403_FORBIDDEN
    default_code = 'wallet_inactive'
    default_message = 'Wallet is inactive or frozen'

    
class InsufficientFundsException(WalletBaseException):
    """Raised when a wallet has insufficient balance."""
    status_code = status.HTTP_400_BAD_REQUEST
    default_code = 'insufficient_funds'
    default_message = 'Insufficient funds'
    
# ============================================================================
# Transaction Exceptions
# ============================================================================

class TransactionException(WalletBaseException):
    """Base class for transaction-related errors."""
    pass

class TransactionNotFoundException(TransactionException):
    """Raised when a transaction is not found."""
    status_code = status.HTTP_404_NOT_FOUND
    default_code = 'transaction_not_found'
    default_message = 'Transaction not found'

class DuplicateTransactionException(TransactionException):
    """Raised when a duplicate idempotency key is detected."""
    status_code = status.HTTP_409_CONFLICT
    default_code = 'duplicate_transaction'
    default_message = 'Transaction already exists with this idempotency key'


class TransactionFailedException(TransactionException):
    """Raised when a transaction fails during processing."""
    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    default_code = 'transaction_failed'
    default_message = 'Transaction processing failed'


class InvalidAmountException(TransactionException):
    """Raised when an invalid amount is provided."""
    status_code = status.HTTP_400_BAD_REQUEST
    default_code = 'invalid_amount'
    default_message = 'Invalid transaction amount'

class IdempotencyKeyMissingException(TransactionException):
    """Raised when idempotency key is required but not provided."""
    status_code = status.HTTP_400_BAD_REQUEST
    default_code = 'idempotency_key_missing'
    default_message = 'Idempotency-Key header is required for this operation'

# ============================================================================
# Reconciliation Exceptions
# ============================================================================

class ReconciliationException(WalletBaseException):
    """Base class for reconciliation errors."""
    pass

class ReconciliationInProgressException(ReconciliationException):
    """Raised when reconciliation is already running."""
    status_code = status.HTTP_409_CONFLICT
    default_code = 'reconciliation_in_progress'
    default_message = 'A reconciliation is already in progress'

class ReconciliationFailedException(ReconciliationException):
    """Raised when reconciliation fails."""
    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    default_code = 'reconciliation_failed'
    default_message = 'Reconciliation process failed'

# ============================================================================
# Rate Limiting Exceptions
# ============================================================================

class RateLimitExceededException(WalletBaseException):
    """Raised when rate limit is exceeded."""
    status_code = status.HTTP_429_TOO_MANY_REQUESTS
    default_code = 'rate_limit_exceeded'
    default_message = 'Too many request. Please try again later.'

# ============================================================================
# Custom Exception Handler
# ============================================================================

def custom_exception_handler(exc, context):
    """
    Custom exception handler for DRF that provides consistent error responses.
    
    Handles:
    - Our custom WalletBaseException hierarchy
    - DRF exceptions
    - Django exceptions
    - Python standard exceptions
    """
    # Get the view and request from context
    view = context.get('view', None)
    request = context.get('request', None)
    
    # Extract request info for logging
    request_info = {}
    if request:
        request_info = {
            'method': request.method,
            'path': request.path,
            'user': str(request.user) if hasattr(request, 'user') else 'anonymous',
            'ip': get_client_ip(request),
        }
    
    # Handle our custom exceptions
    if isinstance(exc, WalletBaseException):
        logger.error(
            "api_error",
            error_type=exc.__class__.__name__,
            message=exc.message,
            code=exc.code,
            **request_info,
            **exc.extra
        )
        
        return Response(
            exc.get_full_details(),
            status=exc.status_code
        )
    
    # Handle DRF's built-in exceptions
    response = exception_handler(exc, context)
    
    if response is not None:
        # Enhance DRF error responses
        error_data = {
            'error': exc.__class__.__name__,
            'code': getattr(exc, 'default_code', 'error'),
            'message': str(exc),
            'details': response.data,
            'status_code': response.status_code
        }
        
        logger.error(
            "drf_error",
            error_type=exc.__class__.__name__,
            message=str(exc),
            **request_info
        )
        
        return Response(error_data, status=response.status_code)
    
    # Handle Django exceptions
    if isinstance(exc, Http404):
        logger.warning(
            "not_found",
            message=str(exc),
            **request_info
        )
        
        return Response(
            {
                'error': 'NotFound',
                'code': 'not_found',
                'message': 'The requested resource was not found',
                'status_code': status.HTTP_404_NOT_FOUND
            },
            status=status.HTTP_404_NOT_FOUND
        )
    
    if isinstance(exc, DjangoValidationError):
        logger.warning(
            "validation_error",
            message=str(exc),
            **request_info
        )
        
        return Response(
            {
                'error': 'ValidationError',
                'code': 'validation_error',
                'message': 'Validation failed',
                'details': exc.message_dict if hasattr(exc, 'message_dict') else {'non_field_errors': exc.messages},
                'status_code': status.HTTP_400_BAD_REQUEST
            },
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # Handle all other exceptions (500 errors)
    logger.exception(
        "unhandled_exception",
        error_type=exc.__class__.__name__,
        message=str(exc),
        **request_info
    )
    
    # In production, don't expose internal error details
    if settings.DEBUG:
        error_message = str(exc)
        error_details = {'traceback': traceback.format_exc()}
    else:
        error_message = 'An internal server error occurred. Please contact support.'
        error_details = {}
    
    return Response(
        {
            'error': 'InternalServerError',
            'code': 'internal_error',
            'message': error_message,
            'details': error_details,
            'status_code': status.HTTP_500_INTERNAL_SERVER_ERROR
        },
        status=status.HTTP_500_INTERNAL_SERVER_ERROR
    )


def get_client_ip(request):
    """Extract client IP from request."""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        return x_forwarded_for.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR')

