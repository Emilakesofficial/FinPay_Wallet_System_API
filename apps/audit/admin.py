"""
Admin configuration for audit app.
"""
from django.contrib import admin
from .models import AuditLog


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    """Admin interface for AuditLog model."""
    list_display = ['actor_email', 'action', 'target_type', 'ip_address', 'created_at']
    list_filter = ['action', 'created_at']
    search_fields = ['actor__email', 'action', 'ip_address']
    readonly_fields = ['id', 'created_at']
    
    def actor_email(self, obj):
        return obj.actor.email if obj.actor else 'System'
    actor_email.short_description = 'Actor'
    
    def target_type(self, obj):
        return obj.content_type.model if obj.content_type else 'N/A'
    target_type.short_description = 'Target Type'
    
    def has_add_permission(self, request):
        # Prevent manual creation
        return False
    
    def has_delete_permission(self, request, obj=None):
        # Prevent deletion
        return False
    
    def has_change_permission(self, request, obj=None):
        # Prevent modification
        return False