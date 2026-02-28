"""
Audit logging model for tracking all actions in the system.
"""
from django.db import models
from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from common.models import BaseModel


class AuditLog(BaseModel):
    """
    Immutable audit trail of all actions in the system.
    
    Tracks WHO did WHAT to WHOM, WHEN, and from WHERE.
    """
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='audit_logs',
        help_text="User who performed the action"
    )
    
    action = models.CharField(
        max_length=100,
        db_index=True,
        help_text="Action performed (e.g., DEPOSIT, WITHDRAW, TRANSFER)"
    )
    
    # Generic foreign key to any model
    content_type = models.ForeignKey(
        ContentType,
        on_delete=models.CASCADE,
        null=True,
        blank=True
    )
    object_id = models.UUIDField(null=True, blank=True)
    target = GenericForeignKey('content_type', 'object_id')
    
    # Capture the state before and after
    old_state = models.JSONField(
        null=True,
        blank=True,
        help_text="State before the action"
    )
    
    new_state = models.JSONField(
        null=True,
        blank=True,
        help_text="State after the action"
    )
    
    # Request metadata
    ip_address = models.GenericIPAddressField(
        null=True,
        blank=True,
        help_text="IP address of the request"
    )
    
    user_agent = models.TextField(
        blank=True,
        help_text="User agent string"
    )
    
    # Additional context
    metadata = models.JSONField(
        default=dict,
        blank=True,
        help_text="Additional metadata"
    )
    
    class Meta:
        db_table = 'audit_logs'
        verbose_name = 'Audit Log'
        verbose_name_plural = 'Audit Logs'
        indexes = [
            models.Index(fields=['-created_at']),
            models.Index(fields=['actor', '-created_at']),
            models.Index(fields=['action', '-created_at']),
            models.Index(fields=['content_type', 'object_id']),
        ]
        # Prevent any modifications
        permissions = [
            ("can_view_sensitive_view_auditlog", "Can view audit logs"),
        ]
    
    def __str__(self):
        actor_name = self.actor.email if self.actor else "System"
        return f"{actor_name} - {self.action} at {self.created_at}"
    
    def save(self, *args, **kwargs):
        """Override save to prevent updates."""
        if self.pk is not None:
            raise ValueError("Audit logs cannot be modified once created")
        super().save(*args, **kwargs)
    
    def delete(self, *args, **kwargs):
        """Override delete to prevent deletion."""
        raise ValueError("Audit logs cannot be deleted")