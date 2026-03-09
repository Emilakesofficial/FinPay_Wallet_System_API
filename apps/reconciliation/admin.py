"""
Reconciliation admin configuration.
"""
from django.contrib import admin
from django.utils.html import format_html
from .models import ReconciliationReport, ReconciliationStatus


@admin.register(ReconciliationReport)
class ReconciliationReportAdmin(admin.ModelAdmin):
    """Admin for reconciliation reports."""
    
    list_display = [
        'id',
        'status_badge',
        'started_at',
        'completed_at',
        'duration_display',
        'run_type',
        'issues_count',
        'triggered_by'
    ]
    
    list_filter = ['status', 'run_type', 'started_at']
    
    search_fields = ['id', 'triggered_by__email']
    
    readonly_fields = [
        'id',
        'run_type',
        'status',
        'started_at',
        'completed_at',
        'duration_seconds',
        'checks_summary_display',
        'discrepancies_display',
        'statistics_display',
        'triggered_by',
        'created_at',
        'updated_at'
    ]
    
    ordering = ['-started_at']
    
    fieldsets = (
        ('Overview', {
            'fields': ('id', 'run_type', 'status', 'triggered_by')
        }),
        ('Timing', {
            'fields': ('started_at', 'completed_at', 'duration_seconds')
        }),
        ('Results', {
            'fields': ('checks_summary_display', 'discrepancies_display', 'statistics_display'),
            'classes': ('collapse',)
        }),
        ('Notes', {
            'fields': ('notes',)
        }),
    )
    
    def status_badge(self, obj):
        """Display status with color."""
        colors = {
            ReconciliationStatus.RUNNING: '#007bff',
            ReconciliationStatus.PASSED: '#28a745',
            ReconciliationStatus.WARNING: '#ffc107',
            ReconciliationStatus.FAILED: '#dc3545',
            ReconciliationStatus.CRITICAL: '#6f42c1',
        }
        color = colors.get(obj.status, '#6c757d')
        return format_html(
            '<span style="background:{}; color:white; padding:3px 8px; '
            'border-radius:3px; font-size:11px;">{}</span>',
            color,
            obj.status
        )
    status_badge.short_description = 'Status'
    
    def duration_display(self, obj):
        """Display duration in readable format."""
        if obj.duration_seconds:
            return f"{obj.duration_seconds:.2f}s"
        return '-'
    duration_display.short_description = 'Duration'
    
    def issues_count(self, obj):
        """Display total issues count."""
        count = obj.total_issues
        if count > 0:
            return format_html(
                '<span style="color:red; font-weight:bold;">{}</span>',
                count
            )
        return format_html('<span style="color:green;">0</span>')
    issues_count.short_description = 'Issues'
    
    def checks_summary_display(self, obj):
        """Display checks summary as formatted HTML."""
        if not obj.checks_summary:
            return '-'
        
        html = '<table style="width:100%;">'
        html += '<tr><th>Check</th><th>Status</th><th>Issues</th></tr>'
        
        for check, summary in obj.checks_summary.items():
            status_color = 'green' if summary.get('passed') else 'red'
            html += f'''
                <tr>
                    <td>{check}</td>
                    <td style="color:{status_color};">{"PASSED" if summary.get("passed") else "FAILED"}</td>
                    <td>{summary.get("issues", 0)}</td>
                </tr>
            '''
        html += '</table>'
        return format_html(html)
    checks_summary_display.short_description = 'Checks Summary'
    
    def discrepancies_display(self, obj):
        """Display discrepancies as formatted HTML."""
        if not obj.discrepancies:
            return 'No issues found'
        
        html = f'<strong>Total: {len(obj.discrepancies)} issues</strong><br><br>'
        html += '<table style="width:100%; font-size:12px;">'
        html += '<tr><th>Check</th><th>Issue</th><th>Details</th></tr>'
        
        for disc in obj.discrepancies[:20]:  # Limit to first 20
            html += f'''
                <tr>
                    <td>{disc.get("check", "-")}</td>
                    <td>{disc.get("issue", "-")}</td>
                    <td style="font-family:monospace; font-size:10px;">{disc}</td>
                </tr>
            '''
        
        if len(obj.discrepancies) > 20:
            html += f'<tr><td colspan="3">... and {len(obj.discrepancies) - 20} more</td></tr>'
        
        html += '</table>'
        return format_html(html)
    discrepancies_display.short_description = 'Discrepancies'
    
    def statistics_display(self, obj):
        """Display statistics as formatted HTML."""
        if not obj.statistics:
            return '-'
        
        html = '<table style="width:50%;">'
        for key, value in obj.statistics.items():
            html += f'<tr><td><strong>{key}</strong></td><td>{value}</td></tr>'
        html += '</table>'
        return format_html(html)
    statistics_display.short_description = 'Statistics'
    
    def has_add_permission(self, request):
        """Prevent manual creation."""
        return False
    
    def has_delete_permission(self, request, obj=None):
        """Prevent deletion."""
        return False
    
    def has_change_permission(self, request, obj=None):
        """Only allow editing notes."""
        return True
    
    def get_readonly_fields(self, request, obj=None):
        """Make all fields readonly except notes."""
        if obj:
            return [f.name for f in obj._meta.fields if f.name != 'notes'] + [
                'checks_summary_display',
                'discrepancies_display', 
                'statistics_display'
            ]
        return self.readonly_fields