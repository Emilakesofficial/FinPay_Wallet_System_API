"""
Admin configuration for reconciliation app.
"""
from django.contrib import admin
from .models import ReconciliationReport


@admin.register(ReconciliationReport)
class ReconciliationReportAdmin(admin.ModelAdmin):
    """Admin interface for ReconciliationReport model."""
    list_display = ['id', 'status', 'run_at', 'completed_at', 'discrepancy_count']
    list_filter = ['status', 'run_at']
    readonly_fields = ['id', 'created_at']
    
    def discrepancy_count(self, obj):
        return len(obj.discrepancies)
    discrepancy_count.short_description = 'Discrepancies'