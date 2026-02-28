"""
Middleware to capture request context for audit logging.
"""
import threading

# Thread-local storage for request context
_thread_locals = threading.local()

def get_current_request():
    """Get the current request from thread-local storage."""
    return getattr(_thread_locals, 'request', None)

def get_client_ip(request):
    """Extract client IP address from request."""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip

class AuditMiddleware:
    """
    Middleware to store request context in thread-local storage.
    This allows the audit service to access request metadata.
    """
    def __init__(self, get_response):
        self.get_response = get_response
    
    def __call__(self, request):
        _thread_locals.request = request
        response = self.get_response(request)
        
        # Clean up after request
        if hasattr(_thread_locals, 'request'):
            del _thread_locals.request
        
        return response