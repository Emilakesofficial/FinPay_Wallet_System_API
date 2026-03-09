"""
Middleware to capture request context for audit logging.
"""
import threading

# Thread-local storage for request context
_thread_locals = threading.local()

def get_request_context():
    """Get the current request from thread-local storage."""
    return {
        'ip_address': getattr(_thread_locals, 'ip_address', None),
        'user_agent': getattr(_thread_locals, 'user_agent', ''),
        'user': getattr(_thread_locals, 'user', None),
    }

def get_client_ip(request):
    """Extract client IP from request headers."""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        return x_forwarded_for.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR')


class AuditMiddleware:
    """
    Middleware to store request context in thread-local storage.
    This allows the audit service to access request metadata.
    """
    def __init__(self, get_response):
        self.get_response = get_response
    
    def __call__(self, request):
        # Store context in thread-local
        _thread_locals.ip_address = get_client_ip(request)
        _thread_locals.user_agent = request.META.get('HTTP_USER_AGENT', '')[:500]
        _thread_locals.user = request.user if hasattr(request, 'user') else None
        
        response = self.get_response(request)
        
        # Cleanup
        _thread_locals.ip_address = None
        _thread_locals.user_agent = ''
        _thread_locals.user = None
        
        return response