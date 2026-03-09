"""Audit services for creating audit logs."""
import logging
from typing import Optional, Dict, Any
from uuid import UUID
from django.contrib.auth import get_user_model

from .models import AuditLog, AuditAction
from .middleware import get_request_context

User = get_user_model()
logger = logging.getLogger(__name__)

class AuditService:
    """Service for creating audit logs."""
    
    @staticmethod
    def log(
        action: AuditAction,
        target_type: str,
        target_id: Optional[UUID] = None,
        actor: Optional[User] = None,
        changes:Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> AuditLog:
        """
        Create an audit log entry.
        Args:
            action: The action being performed
            target_type: Type of entity (model) affected
            target_id: ID of affected entity
            actor: User performing the action (auto-detected if None)
            changes: Dict of changes made
            metadata: Additional context
        Returns:
            AuditLog: The created audit log
        """
        
        # Get request context
        context = get_request_context()
        
        # Use provided actor or get from context
        if actor is None:
            actor = context.get('user')
            if actor and not actor.is_authenticated:
                actor=None
                
        try:
            audit_log = AuditLog.objects.create(
                actor=actor,
                action=action,
                target_type=target_type,
                target_id=target_id,
                changes=changes or {},
                ip_address=context.get('ip_address'),
                user_agent=context.get('user_agent', ''),
                metadata=metadata or {},
            )
            
            logger.debug(f"Action log created: {audit_log.id}")
            return audit_log
        except Exception as e:
            logger.error(f"Failed to create audit log: {e}")
            return None
        
    @staticmethod
    def log_deposit(transaction, actor):
        """Log a deposit action."""
        return AuditService.log(
            action=AuditAction.DEPOSIT,
            target_type='Transaction',
            target_id=transaction.id,
            actor=actor,
            changes={
                'amount': str(transaction.amount),
                'currency': transaction.currency,
                'wallet_id': str(transaction.metadata.get('wallet_id', '')),
                'reference': transaction.reference,
            },
        )
        
    @staticmethod
    def log_withdrawal(transaction, actor):
        """Log a withdrawal action."""
        return AuditService.log(
            action=AuditAction.WITHDRAWAL,
            target_type='Transaction',
            target_id=transaction.id,
            actor=actor,
            changes={
                'amount': str(transaction.amount),
                'currency': transaction.currency,
                'wallet_id': str(transaction.metadata.get('wallet_id', '')),
                'reference': transaction.reference,
            },
        )
    
    @staticmethod
    def log_transfer(transaction, actor):
        """Log a transfer action."""
        return AuditService.log(
            action=AuditAction.TRANSFER,
            target_type='Transaction',
            target_id=transaction.id,
            actor=actor,
            changes={
                'amount': str(transaction.amount),
                'currency': transaction.currency,
                'from_wallet_id': str(transaction.metadata.get('from_wallet_id', '')),
                'to_wallet_id': str(transaction.metadata.get('to_wallet_id', '')),
                'reference': transaction.reference,
            },
        )
        
    @staticmethod
    def log_wallet_created(wallet, actor):
        """Log wallet creation."""
        return AuditService.log(
            action=AuditAction.WALLET_CREATED,
            target_type='Wallet',
            target_id=wallet.id,
            actor=actor,
            changes={
                'currency': wallet.currency,
                'name': wallet.name,
            },
        )
        
    @staticmethod
    def log_user_registered(user):
        """Log user registration."""
        return AuditService.log(
            action=AuditAction.USER_REGISTERED,
            target_type='User',
            target_id=user.id,
            actor=user,
            changes={
                'email': user.email,
                'username': user.username,
            },
        )
        
    @staticmethod
    def log_user_login(user):
        """Log user login."""
        return AuditService.log(
            action=AuditAction.USER_LOGIN,
            target_type='User',
            target_id=user.id,
            actor=user,
        )
        
    @staticmethod
    def log_user_logout(user):
        """Log user logout."""
        return AuditService.log(
            action=AuditAction.USER_LOGOUT,
            target_type='User',
            target_id=user.id,
            actor=user,
        )
        
    @staticmethod
    def log_password_changed(user):
        """Log password change."""
        return AuditService.log(
            action=AuditAction.PASSWORD_CHANGED,
            target_type='User',
            target_id=user.id,
            actor=user,
        )
        
    @staticmethod
    def log_profile_updated(user):
        """Log profile updated."""
        return AuditService.log(
            action=AuditAction.PROFILE_UPDATED,
            target_type='User',
            target_id=user.id,
            actor=user,
        )