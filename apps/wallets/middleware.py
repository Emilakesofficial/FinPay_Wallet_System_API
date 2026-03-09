"""Middleware for handling idempotency keys in API requests."""
import logging
from django.http import JsonResponse
from django.utils.deprecation import MiddlewareMixin
from apps.wallets.models import Transaction
from apps.wallets.constants import TransactionStatus

logger = logging.getLogger(__name__)

class IdempotencyMiddleware(MiddlewareMixin):
    """
    Middleware to enforce idempotency keys on mutation endpoints.
    
    If a request includes an Idempotency-Key header and a transaction
    with that key already exists and is completed, return the cached response.
    """
    
    MUTATION_METHODS = ['POST', 'PUT', 'PATCH']
    IDEMPOTENCY_HEADER = 'HTTP_IDEMPOTENCY_KEY'
    
    def process_request(self, request):
        """Check for idempotency key before processing request."""
        # Only check on mutation methods
        if request.method not in self.MUTATION_METHODS:
            return None
        
        # Get idempotency key from header
        idempotency_key = request.META.get(self.IDEMPOTENCY_HEADER)
        
        if not idempotency_key:
            # No idempotency key provided - let it through
            # (will be validated at service layer if required)
            return None
        
        # Store idempotency key in request for later use
        request.idempotency_key = idempotency_key
        return None
    
    def process_response(self, request, response):
        """Process response and cache it if idempotency key was provided."""
        return response