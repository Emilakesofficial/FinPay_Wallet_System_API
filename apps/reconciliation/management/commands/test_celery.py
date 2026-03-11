from django.core.management.base import BaseCommand
from apps.reconciliation.tasks import send_reconciliation_alert

class Command(BaseCommand):
    help = 'Test Celery task execution'
    
    def handle(self, *args, **options):
        self.stdout.write('Sending test task...')
        
        # Try to send a simple task
        from config.celery import app
        
        # Method 1: Using the app instance
        result = app.send_task(
            'apps.reconciliation.tasks.send_reconciliation_alert',
            args=['test-report-id']
        )
        self.stdout.write(f'Task sent via send_task: {result.id}')
        
        # Method 2: Using delay
        result2 = send_reconciliation_alert.delay('test-report-id-2')
        self.stdout.write(f'Task sent via delay: {result2.id}')