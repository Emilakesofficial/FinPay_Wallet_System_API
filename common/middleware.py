"""Middleware for error tracking and request context."""
import uuid
import structlog
from django.utils.deprecation import MiddlewareMixin
from structlog.contextvars import bind_contextvars, clear_contextvars

logger = structlog.get_logger(__name__)

class RequestIDMiddleware(MiddlewareMixin):
    """Adds a unique request ID to every request.
    Useful for tracing requests across logs."""
    
    def process_request(self, request):
        request_id = request.META.get('HTTP_X_REQUEST_ID', str(uuid.uuid4))
        request.request_id = request_id
        
        # Add to structlog context
        bind_contextvars(
            request_id=request_id,
            method=request.method,
            path=request.path,
            user=str(request.user) if hasattr(request, 'user') and request.user.is_authenticated else 'anonymous'
        )
    
    def process_response(self, request, response):
        # Add request ID to response headers
        if hasattr(request, 'request_id'):
            response['X-Request-ID'] = request.request_id
        
        # Clear context
        clear_contextvars()
        
        return response
    
class ExceptionLoggingMiddleware(MiddlewareMixin):
    """Logs all exceptions with full context."""
    def process_exception(self, request, exception):
        logger.exception(
            "middleware_exception",
            exception_type=exception.__class__.__name__,
            exception_message=str(exception),
            path=request.path,
            method=request.methods,
            user=str(request.user) if hasattr(request, 'user') else 'anonymous',
        )
        # Return None to let Django's exception handling continue
        return None