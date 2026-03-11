# apps/reconciliation/management/commands/cleanup_stuck_reports.py

from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from apps.reconciliation.models import ReconciliationReport, ReconciliationStatus


class Command(BaseCommand):
    help = 'Clean up stuck reconciliation reports'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--minutes',
            type=int,
            default=10,
            help='Mark reports as failed if running longer than X minutes'
        )
    
    def handle(self, *args, **options):
        minutes = options['minutes']
        cutoff = timezone.now() - timedelta(minutes=minutes)
        
        stuck_reports = ReconciliationReport.objects.filter(
            status__in=[ReconciliationStatus.RUNNING, ReconciliationStatus.PENDING],
            started_at__lt=cutoff
        )
        
        count = stuck_reports.count()
        
        if count == 0:
            self.stdout.write(self.style.SUCCESS('No stuck reports found'))
            return
        
        self.stdout.write(f'Found {count} stuck reports')
        
        for report in stuck_reports:
            report.status = ReconciliationStatus.FAILED
            report.completed_at = timezone.now()
            report.save()
            self.stdout.write(f'  - Marked report {report.id} as FAILED')
        
        self.stdout.write(self.style.SUCCESS(f'Cleaned up {count} stuck reports'))