"""
Reconciliation models for detecting and tracking discrepancies.
"""
from django.db import models
from common.models import BaseModel

class ReconciliationType(models.TextChoices):
    """Types of reconciliation runs"""
    SCHEDULED = 'SCHEDULED', 'Scheduled(Daily)'
    MANUAL = 'MANUAL', 'Manual Trigger'
    POST_TRANSACTION = 'POST_TRANSACTION', 'Post-Transaction'

class ReconciliationStatus(models.TextChoices):
    """Status of a reconciliation run."""
    RUNNING = 'RUNNING', 'Running'
    PASSED = 'PASSED', 'Passed'
    WARNING = 'WARNING', 'Warning'
    FAILED = 'FAILED', 'Failed'
    CRITICAL = 'CRITICAL', 'Critical'
    PENDING = 'PENDING', 'Pending'


class ReconciliationReport(BaseModel):
    """
    Report from a reconciliation run.
    Stores the results of various reconciliation checks and any
    discrepancies found.
    """
    run_type = models.CharField(
        max_length=20,
        choices=ReconciliationType.choices,
        default=ReconciliationType.SCHEDULED
    )
    status = models.CharField(
        max_length=20,
        choices=ReconciliationStatus.choices,
        default=ReconciliationStatus.RUNNING,
        db_index=True,
        null=True,
        help_text="Status of this reconciliation run"
    )
    started_at = models.DateTimeField(auto_now_add=True, db_index=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    duration_seconds = models.FloatField(null=True, blank=True)
    
    # Check results summary
    checks_summary = models.JSONField(
        default=dict,
        blank=True,
        help_text="Summary of each check (passed/failed, issue count)"
    )
    
    # Detailed discrepancies
    discrepancies = models.JSONField(
        default=list,
        blank=True,
        help_text="List of all issues found"
    )
    
    # Statistics
    statistics = models.JSONField(
        default=dict,
        blank=True,
        help_text="Overall system statistics"
    )
    
    # Admin notes
    notes = models.TextField(
        blank=True,
        help_text="Admin notes or actions taken"
    )
    
    # Triggered by
    triggered_by = models.ForeignKey(
        'accounts.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='reconciliation_reports'
    )
    
    class Meta:
        db_table = 'reconciliation_reports'
        verbose_name = 'Reconciliation Report'
        verbose_name_plural = 'Reconciliation Reports'
        indexes = [
            models.Index(fields=['-started_at']),
            models.Index(fields=['status', '-started_at']),
        ]
    
    def __str__(self):
        return f"Reconciliation {self.started_at.strftime('%Y-%m-%d %H:%M')} - {self.status}"
    
    @property
    def total_issues(self):
        """Count total issues found."""
        return len(self.discrepancies)
    
    @property
    def is_healthy(self):
        """Check if reconciliation passed."""
        return self.status == ReconciliationStatus.PASSED
