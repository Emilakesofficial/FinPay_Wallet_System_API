"""
Reconciliation models for detecting and tracking discrepancies.
"""
from django.db import models
from common.models import BaseModel

class ReconciliationStatus(models.TextChoices):
    """Status of a reconciliation run."""
    RUNNING = 'RUNNING', 'Running'
    PASSED = 'PASSED', 'Passed'
    FAILED = 'FAILED', 'Failed'

class ReconciliationReport(BaseModel):
    """
    Report from a reconciliation run.
    
    Stores the results of various reconciliation checks and any
    discrepancies found.
    """
    status = models.CharField(
        max_length=20,
        choices=ReconciliationStatus.choices,
        default=ReconciliationStatus.RUNNING,
        help_text="Status of this reconciliation run"
    )
    run_at = models.DateTimeField(
        auto_now_add=True,
        help_text="When this reconciliation was run"
    )
    completed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When this reconciliation completed"
    )
    checks_performed = models.JSONField(
        default=list,
        help_text="List of checks performed"
    )
    discrepancies = models.JSONField(
        default=list,
        help_text="List of discrepancies found"
    )
    summary = models.JSONField(
        default=dict,
        help_text="Summary statistics"
    )
    notes = models.TextField(
        blank=True,
        help_text="Additional notes"
    )
    
    class Meta:
        db_table = 'reconciliation_reports'
        verbose_name = 'Reconciliation Report'
        verbose_name_plural = 'Reconciliation Reports'
        indexes = [
            models.Index(fields=['-run_at']),
            models.Index(fields=['status']),
        ]
    
    def __str__(self):
        return f"Reconciliation {self.run_at} - {self.status}"