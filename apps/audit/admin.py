"""
Audit admin configuration.
"""
from django.contrib import admin
from .models import AuditLog


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    """Admin for audit logs."""
    
    list_display = ['created_at', 'actor_email', 'action', 'target_type', 'target_id', 'ip_address']
    list_filter = ['action', 'target_type', 'created_at']
    search_fields = ['actor__email', 'ip_address', 'target_id']
    readonly_fields = ['id', 'actor', 'action', 'target_type', 'target_id', 
                       'changes', 'ip_address', 'user_agent', 'metadata', 'created_at']
    ordering = ['-created_at']
    
    def actor_email(self, obj):
        return obj.actor.email if obj.actor else 'System'
    actor_email.short_description = 'Actor'
    
    def has_add_permission(self, request):
        return False
    
    def has_change_permission(self, request, obj=None):
        return False
    
    def has_delete_permission(self, request, obj=None):
        return False