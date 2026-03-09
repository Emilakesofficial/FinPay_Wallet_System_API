"""
Audit logging model for tracking all actions in the system.
"""
from django.db import models
from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from common.models import BaseModel

class AuditAction(models.TextChoices):
    """Audit action types"""
    # Auth actions
    USER_REGISTERED = 'USER_REGISTERED', 'User Registered'
    USER_LOGIN = 'USER_LOGIN', 'User Login',
    USER_LOGOUT = 'USER_LOGOUT', 'User Logout',
    PROFILE_UPDATED = 'PROFILE_UPDATED', 'Profile Updated',
    PASSWORD_CHANGED = 'PASSWORD_CHANGED', 'Password Changed'
    
    # Wallet actions
    WALLET_CREATED = 'WALLET_CREATED', 'Wallet Created'
    
    #Transaction actions
    DEPOSIT = 'DEPOSIT', 'Deposit'
    WITHDRAWAL = 'WITHDRAWAL', 'Withdrawal'
    TRANSFER = 'TRANSFER', 'Transfer'
    
    #Admin actions
    RECONCILIATION_RUN = 'RECONCILIATION_RUN', 'Reconciliation Run'
    BALANCE_DRIFT_FIXED = 'BALANCE_DRIFT_FIXED', 'Balance Drift Fixed'



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
    target_type = models.CharField(
        max_length=50,
        db_index=True,
        help_text="Type of entity affected (e.g., Wallet, Transaction)"
    )
    target_id = models.UUIDField(
        null=True,
        blank=True,
        db_index=True,
        help_text="ID of the affected entity"
    )
    changes = models.JSONField(
        default=dict,
        blank=True,
        help_text="Details of the change"
    )
    ip_address = models.GenericIPAddressField(
        null=True,
        blank=True,
        help_text="IP address of the request"
    )
    
    user_agent = models.TextField(
        blank=True,
        default='',
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
        ordering = ['-created_at']
        verbose_name = 'Audit Log'
        verbose_name_plural = 'Audit Logs'
        indexes = [
            models.Index(fields=['-created_at']),
            models.Index(fields=['actor', '-created_at']),
            models.Index(fields=['action', '-created_at']),
            models.Index(fields=['target_type', 'target_id']),
        ]
        
    def __str__(self):
        actor_name = self.actor.email if self.actor else "System"
        return f"{actor_name} - {self.action} at {self.created_at}"
    
    def save(self, *args, **kwargs):
        """Prevent updates to audit logs."""
        if self._state.adding:
            super().save(*args, **kwargs)
        else:
            # This is an update - block it
            raise ValueError("Audit logs cannot be modified once created")
    
    def delete(self, *args, **kwargs):
        """Prevent deletion of audit logs."""
        raise ValueError("Audit logs cannot be deleted")