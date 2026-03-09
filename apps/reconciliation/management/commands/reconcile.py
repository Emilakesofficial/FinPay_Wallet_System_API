"""Management command to run reconciliation manually."""
from django.core.management.base import BaseCommand
from config.celery import app

class Command(BaseCommand):
    help = 'Run reconciliation checks manually'
    
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--async',
            action='store_true',
            dest='run_async',
            help='Run asynchronously {using Celery}',
        )
        
    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('Starting reconciliation...'))
        
        if options['run_async']:
            # Use send_task for reliable delivery
            result = app.send_task(
                'apps.reconciliation.tasks.run_reconciliation',
                kwargs={'run_type': 'MANUAL'}
            )
            self.stdout.write(
                self.style.SUCCESS(f'Reconciliation task queued: {result.id}')
            )
        else:
            # Run synchronously
            from apps.reconciliation.tasks import run_reconciliation
            report_id = run_reconciliation(run_type='MANUAL')
            self.stdout.write(
                self.style.SUCCESS(f'Reconciliation completed: Report ID {report_id}')
            )