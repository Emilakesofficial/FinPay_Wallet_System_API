"""Custom throttle classes for rate limiting."""
from rest_framework.throttling import UserRateThrottle, AnonRateThrottle

class BurstRateThrottle(UserRateThrottle):
    """Burst rate limiting rapid-fire requests.
    60 requests per minute"""
    scope = 'burst'
    
class SustainedRateThrottle(UserRateThrottle):
    """Sustained rate limiting - prevents high volume over time.
    1000 requests per hour"""
    scope = 'sustained'
    
class TransactionRateThrottle(UserRateThrottle):
    """Transaction-specific rate limiting. Stricter limits for financial operations."""
    scope = 'transactions'
    
class AuthRateThrottle(AnonRateThrottle):
    """Authentication endpoint rate limiting.
    Prevents brute force attacks."""
    scope = 'auth'
    
class ReconciliationRateThrottle(UserRateThrottle):
    """Reconciliation rate limit"""
    scope = 'reconciliation_trigger'