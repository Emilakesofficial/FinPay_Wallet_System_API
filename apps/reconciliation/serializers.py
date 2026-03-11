"""Serializers for reconciliation API"""
from rest_framework import serializers
from .models import ReconciliationReport, ReconciliationStatus, ReconciliationType

class ReconciliationReportSerializer(serializers.ModelSerializer):
    """Serializer for reconciliation reports"""
    triggered_by_email = serializers.SerializerMethodField()
    total_issues = serializers.SerializerMethodField()
    is_healthy = serializers.SerializerMethodField()
    
    class Meta:
        model = ReconciliationReport
        fields = [
            'id',
            'run_type',
            'status',
            'started_at',
            'completed_at',
            'duration_seconds',
            'checks_summary',
            'discrepancies',
            'statistics',
            'notes',
            'triggered_by',
            'triggered_by_email',
            'total_issues',
            'is_healthy',
            'created_at',
            'updated_at'
        ]
        read_only_fields = [
            'id', 'run_type', 'status', 'started_at', 'completed_at',
            'duration_seconds', 'checks_summary', 'discrepancies',
            'statistics', 'triggered_by', 'created_at', 'updated_at'
        ]
        
    def get_triggered_by_email(self, obj):
        """Get email of user who triggered reconciliation."""
        return obj.triggered_by.email if obj.triggered_by else None
    
    def get_total_issues(self, obj) -> int:
        """Get total number of issues found."""
        return obj.total_issues
    
    def get_is_healthy(self, obj):
        """Check if reconciliation passed."""
        return obj.is_healthy
    
class ReconciliationReportListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for list view."""
    
    triggered_by_email = serializers.SerializerMethodField()
    total_issues = serializers.IntegerField(read_only=True)
    
    class Meta:
        model = ReconciliationReport
        fields = [
            'id',
            'run_type',
            'status',
            'started_at',
            'completed_at',
            'duration_seconds',
            'total_issues',
            'triggered_by_email',
        ]
        read_only_fields = [
            'id',
            'run_type',
            'status',
            'started_at',
            'completed_at',
            'duration_seconds',
            'total_issues',
            'triggered_by_email',
        ]
    
    def get_triggered_by_email(self, obj) -> str:
        return obj.triggered_by.email if obj.triggered_by else None

class TriggerReconciliationSerializer(serializers.Serializer):
    """Serializer for triggering reconciliation."""
    
    run_type = serializers.ChoiceField(
        choices=ReconciliationType.choices,
        default=ReconciliationType.MANUAL
    )
    
class ReconciliationStatusSerializer(serializers.Serializer):
    """Serializer for current reconciliation status."""
    
    is_running = serializers.BooleanField()
    latest_report = ReconciliationReportListSerializer(
        allow_null=True,
        read_only=True
    )
    total_reports = serializers.IntegerField()
    last_24h_reports = serializers.IntegerField()
    health_summary = serializers.DictField()

class ReconciliationSummarySerializer(serializers.Serializer):
    """Serializer for reconciliation summary statistics."""
    
    total_reports = serializers.IntegerField()
    reports_last_7d = serializers.IntegerField()
    reports_last_30d = serializers.IntegerField()
    
    status_breakdown = serializers.DictField()
    average_duration = serializers.FloatField()
    
    latest_report = ReconciliationReportListSerializer(
        allow_null=True,
        read_only=True
    )
    recent_failures = serializers.ListField(
        child=serializers.DictField(),
        read_only=True
    )

        