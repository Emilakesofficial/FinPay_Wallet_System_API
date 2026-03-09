"""Celery configuration for wallet system"""
import os
from celery import Celery
from celery.schedules import crontab

# Set default django settings
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.development')

app = Celery('wallet_system')

# Load config from Django settings 
app.config_from_object('django.conf:settings', namespace='CELERY')

# Auto-discover tasks from all installed apps
app.autodiscover_tasks()

# Auto-discover tasks from installed apps
app.conf.beat_schedule = {
    'daily-reconciliation': {
        'task': 'apps.reconciliation.tasks.run_reconciliation',
        'schedule': crontab(hour=2, minute=0), # 2AM daily
        'options': {
            'expires': 3600, # Task expires after 1 hour
        }
    },
}

#Timezone
app.conf.timezone = 'UTC'

@app.task(bind=True, ignore_result=True)
def debug_task(self):
    """Debug task to test Celery."""
    print(f"Request: {self.request!r}")