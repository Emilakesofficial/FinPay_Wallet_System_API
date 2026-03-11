"""Management command to run reconciliation manually."""
from django.core.management.base import BaseCommand
from config.celery import app
from django.utils import timezone
from apps.reconciliation.models import ReconciliationReport, ReconciliationStatus
from apps.reconciliation.tasks import run_reconciliation

class Command(BaseCommand):
    help = 'Run reconciliation checks manually'
    
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--async',
            action='store_true',
            dest='run_async',
            help='Run asynchronously using Celery',
        )
        parser.add_argument(
            '--wait',
            action='store_true',
            dest='wait_result',
            help='Wait for task to finish and show result (for local testing)',
        )
        
    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('Starting reconciliation...'))
        
        # Create the report first
        report = ReconciliationReport.objects.create(
            run_type='MANUAL',
            status=ReconciliationStatus.PENDING,
            started_at=timezone.now()
        
        )
        report_id = str(report.id)
        
        self.stdout.write(
            self.style.SUCCESS(f'Created report: {report_id}')
        )
        
        if options['run_async']:  
            # Queue the task
            result = run_reconciliation.delay(
                run_type='MANUAL',
                report_id=report_id
            )
            
            self.stdout.write(
                self.style.SUCCESS(f'Task queued: {result.id}')
            )
            
            # Optionally wait for result
            if options['wait_result']:
                self.stdout.write(self.style.WARNING('Waiting for task to finish...'))
                try:
                    final_report_id = result.get(timeout=300)  # 5 min timeout
                    self.stdout.write(
                        self.style.SUCCESS(f'Task completed. Report ID: {final_report_id}')
                    )
                except Exception as e:
                    self.stdout.write(
                        self.style.ERROR(f'Task failed: {str(e)}')
                    )
        else:
            # Run synchronously
            try:
                final_report_id = run_reconciliation(
                    run_type='MANUAL',
                    report_id=report_id
                )
                self.stdout.write(
                    self.style.SUCCESS(f'Reconciliation completed: {final_report_id}')
                )
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f'Reconciliation failed: {str(e)}')
                )