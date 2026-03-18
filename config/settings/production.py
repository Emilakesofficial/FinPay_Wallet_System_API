"""Production-specific settings.

This file makes production-safe defaults and reads sensitive/operational
configuration from environment variables so containers and deployments
can configure behavior without code changes.
"""

from .base import *

# Debug and hosts
DEBUG = env.bool('DEBUG', default=False)
ALLOWED_HOSTS =["*"]     #env.list('ALLOWED_HOSTS', default=['finpay-f9zx.onrender.com'])

# Security settings (override via env if needed)
# SECURE_SSL_REDIRECT = env.bool('SECURE_SSL_REDIRECT', default=False)
# SECURE_HSTS_SECONDS = env.int('SECURE_HSTS_SECONDS', default=31536000)
# SECURE_HSTS_INCLUDE_SUBDOMAINS = env.bool('SECURE_HSTS_INCLUDE_SUBDOMAINS', default=True)
# SECURE_HSTS_PRELOAD = env.bool('SECURE_HSTS_PRELOAD', default=True)
# SESSION_COOKIE_SECURE = env.bool('SESSION_COOKIE_SECURE', default=False)
# CSRF_COOKIE_SECURE = env.bool('CSRF_COOKIE_SECURE', default=False)
# SECURE_BROWSER_XSS_FILTER = env.bool('SECURE_BROWSER_XSS_FILTER', default=True)
# SECURE_CONTENT_TYPE_NOSNIFF = env.bool('SECURE_CONTENT_TYPE_NOSNIFF', default=True)
# X_FRAME_OPTIONS = env('X_FRAME_OPTIONS', default='DENY')

# CSRF trusted origins (useful behind proxies/load-balancers)
# CSRF_TRUSTED_ORIGINS = env.list('CSRF_TRUSTED_ORIGINS', default=[])

# Database settings - prefer DATABASE_URL but keep individual vars as fallback
_database_url = env('DATABASE_URL', default=None)
if _database_url:
	DATABASES['default'] = env.db()

# Ensure connection pooling value is configurable
DATABASES['default']['CONN_MAX_AGE'] = env.int('CONN_MAX_AGE', default=600)
DATABASES['default'].setdefault('ATOMIC_REQUESTS', True)

# Static files - allow overriding target via env
STATIC_URL = env('STATIC_URL', default='static/')
STATIC_ROOT = Path(env('STATIC_ROOT', default=str(BASE_DIR / 'staticfiles')))
STATICFILES_STORAGE = env('STATICFILES_STORAGE', default='whitenoise.storage.CompressedManifestStaticFilesStorage')

# Email configuration (configure based on your email service)
EMAIL_BACKEND = env('EMAIL_BACKEND', default='django.core.mail.backends.smtp.EmailBackend')
EMAIL_HOST = env('EMAIL_HOST', default='')
EMAIL_PORT = env.int('EMAIL_PORT', default=587)
EMAIL_USE_TLS = env.bool('EMAIL_USE_TLS', default=True)
EMAIL_HOST_USER = env('EMAIL_HOST_USER', default='')
EMAIL_HOST_PASSWORD = env('EMAIL_HOST_PASSWORD', default='')
DEFAULT_FROM_EMAIL = env('DEFAULT_FROM_EMAIL', default=DEFAULT_FROM_EMAIL)
