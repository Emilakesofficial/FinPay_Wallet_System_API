"""Celery configuration for wallet system"""
import os
from celery import Celery
from celery.schedules import crontab
from django.db import connection
from celery.signals import task_postrun
from celery.signals import task_failure, task_success, task_retry
import logging

logger = logging.getLogger(__name__)

# Set default django settings
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.development')

app = Celery('wallet_system')

# Load config from Django settings 
app.config_from_object('django.conf:settings', namespace='CELERY')

app.conf.broker_connection_retry_on_startup = True

# Configuration for single-container deployment
app.conf.update(
    broker_connection_retry_on_startup=True,
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
    
    # Important: Optimize for shared container
    worker_prefetch_multiplier=1,  # Fetch one task at a time
    worker_max_tasks_per_child=50,  # Restart worker after 100 tasks (prevent memory leaks)
    task_acks_late=True,  # Acknowledge tasks after completion
    task_reject_on_worker_lost=True,  # Re-queue if worker crashes
    
    # Connection pool settings
    broker_pool_limit=1,  # Limit connections in shared environment
    broker_heartbeat=None,
    broker_connection_timeout=30,
    result_backend_transport_options={'master_name': 'mymaster'},
    
    # Task time limits
    task_time_limit=300,  # 5 minutes hard limit
    task_soft_time_limit=240,  # 4 minutes soft limit
)

# Auto-discover tasks from all installed apps
app.autodiscover_tasks()

# Auto-discover tasks from installed apps
app.conf.beat_schedule = {
    'daily-reconciliation': {
        'task': 'apps.reconciliation.tasks.run_reconciliation',
        'schedule': crontab(hour=2, minute=0),  # 2AM daily
        'kwargs': {
            'run_type': 'SCHEDULED',
            'report_id': None  # Will be created by the task
        },
        'options': {
            'expires': 3600,
        }
    },
}

#Timezone
app.conf.timezone = 'UTC'

app.conf.worker_pool_retries = True

@app.task(bind=True)
def cleanup_after_task(self):
    """Close DB connections to prevent pool exhaustion"""
    connection.close()
    
@task_postrun.connect
def close_db_connection(**kwargs):
    connection.close()

@task_failure.connect
def task_failure_handler(sender=None, task_id=None, exception=None, **kwargs):
    """Log task failures."""
    logger.error(f"Task {sender.name}[{task_id}] failed: {exception}")
    # TODO: Send to monitoring service (Sentry, Datadog, etc.)

@task_retry.connect
def task_retry_handler(sender=None, task_id=None, reason=None, **kwargs):
    """Log task retries."""
    logger.warning(f"Task {sender.name}[{task_id}] retrying: {reason}")

@task_success.connect
def task_success_handler(sender=None, result=None, **kwargs):
    """Log successful tasks."""
    logger.info(f"Task {sender.name} completed successfully")

@app.task(bind=True, ignore_result=True)
def debug_task(self):
    """Debug task to test Celery."""
    print(f"Request: {self.request!r}")