'''Settings module selector based on DJANGO_SETTINGS_MODULE environment variable.'''
import os

environment  = os.getenv('DJANGO_ENVIRONMENT', 'development')

if environment == 'production':
    from .production import *
else:
    from .development import *