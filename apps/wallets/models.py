"""
Core wallet models implementing double-entry bookkeeping.

Key principles:
1. Wallet has NO balance field - balance is computed from ledger entries
2. Every transaction creates exactly 2 ledger entries (debit + credit)
3. Ledger entries are immutable (no updates or deletes)
4. Running balance is cached in LedgerEntry.balance_after for performance
"""

from decimal import Decimal
from django.db import models
from django.conf import settings
from django.core.validators import MinValueValidator
from common.models import BaseModel
from .constants import TransactionType, TransactionStatus, EntryType

from django.db.models import Sum, Q, DecimalField
from django.db.models.functions import Coalesce

class Wallet(BaseModel):
    """
    A wallet belonging to a user or the system.
    
    IMPORTANT: No balance field! Balance is computed from LedgerEntry records.
    This is the ONLY way to prevent balance drift and race conditions.
    """
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT, # never delete a user with a wallet
        related_name='wallets',
        null=True,
        blank=True,
        help_text="Owner of the wallet (null for system wallets)"
    )
    currency = models.CharField(
        max_length=3,
        default=settings.WALLET_CURRENCY,
        help_text="Currency code (ISO 4217)"
    )
    is_system = models.BooleanField(
        default=False,
        db_index=True,
        help_text="True if this is a system wallet (for deposits/withdrawals)"
    )
    name = models.CharField(
        max_length=100,
        help_text="Wallet name/description"
    )
    class Meta:
        db_table = 'wallets'
        verbose_name = 'Wallet'
        verbose_name_plural = 'Wallets'
        indexes = [
            models.Index(fields=['user', 'currency']),
            models.Index(fields=['is_system']),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'currency'],
                name='unique_user_currency_wallet',
                condition=models.Q(is_system=False)
            ),
            models.CheckConstraint(
                check=models.Q(is_system=True, user__isnull=True) | 
                      models.Q(is_system=False, user__isnull=False),
                name='system_wallet_has_no_user'
            ),
        ]
        
    def __str__(self):
        if self.is_system:
            return f"System Wallet: {self.name}"
        return f"Wallet: {self.user} ({self.currency})"
    
    def get_balance(self) -> Decimal:
        """
        Get current balance by reading the latest ledger entry's balance_after.
        This is fast and consistent with the ledger.
        
        Returns:
            Decimal: Current balance
        """
        latest_entry = self.ledger_entries.order_by('-created_at').first()
        return latest_entry.balance_after if latest_entry else Decimal('0.00')
    
    def compute_balance(self) -> Decimal:
        """
        Compute balance from scratch by summing all ledger entries.
        Used for reconciliation and verification.
        
        Returns:
            Decimal: Computed balance (credits - debits)
        """
        
        aggregates = self.ledger_entries.aggregate(
            total_credits=Coalesce(
                Sum('amount', filter=Q(entry_type=EntryType.CREDIT)),
                Decimal('0.00'),
                output_field=DecimalField()
            ),
            total_debits=Coalesce(
                Sum('amount', filter=Q(entry_type=EntryType.DEBIT)),
                Decimal('0.00'),
                output_field=DecimalField()
            )
        )
        return aggregates['total_credits'] - aggregates['total_debits']
    
class Transaction(BaseModel):
    """
    Represents a financial transaction (deposit, withdrawal, or transfer).
    
    Every transaction has an idempotency_key to prevent duplicate processing.
    Status tracks the lifecycle: PENDING → COMPLETED or FAILED.
    """
    
    idempotency_key = models.CharField(
        max_length=255,
        unique=True,
        db_index=True,
        help_text="Unique key to prevent duplicate transactions"
    )
    
    transaction_type = models.CharField(
        max_length=20,
        choices=TransactionType.choices,
        help_text="Type of transaction"
    )
    status = models.CharField(
        max_length=20,
        choices=TransactionStatus.choices,
        default=TransactionStatus.PENDING,
        db_index=True,
        help_text="Current status of the transaction"
    )
    amount = models.DecimalField(
        max_digits=settings.WALLET_MAX_DIGITS,
        decimal_places=settings.WALLET_DECIMAL_PLACES,
        validators=[MinValueValidator(Decimal('0.01'))],
        help_text="Transaction amount"
    )
    currency = models.CharField(
        max_length=3,
        default=settings.WALLET_CURRENCY,
        help_text="Currency code"
    )
    reference = models.CharField(
        max_length=100,
        unique=True,
        db_index=True,
        help_text="Human-readable transaction reference"
    )
    description = models.TextField(
        blank=True,
        help_text="Transaction description"
    )
    metadata = models.JSONField(
        default=dict,
        blank=True,
        help_text="Additional transaction metadata"
    )
    # Track who initiated the transaction
    initiated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='initiated_transactions',
        null=True,
        blank=True,
        help_text="User who initiated the transaction"
    )
    class Meta:
        db_table = 'transactions'
        verbose_name = 'Transaction'
        verbose_name_plural = 'Transactions'
        indexes = [
            models.Index(fields=['-created_at']),
            models.Index(fields=['status', '-created_at']),
            models.Index(fields=['transaction_type', '-created_at']),
        ]
        
    def __str__(self):
        return f"{self.transaction_type}: {self.amount} {self.currency} ({self.status})"

class LedgerEntry(BaseModel):
    """
    Individual ledger entry implementing double-entry bookkeeping.
    
    CRITICAL RULES:
    1. Entries are IMMUTABLE - never update or delete
    2. Every transaction creates exactly 2 entries (1 debit, 1 credit)
    3. balance_after is a running balance cache for performance
    4. The sum of all entries for a wallet = current balance
    """
    
    wallet = models.ForeignKey(
        Wallet,
        on_delete=models.PROTECT,  # Never delete wallets with entries
        related_name='ledger_entries',
        help_text="Wallet this entry belongs to"
    )
    transaction = models.ForeignKey(
        Transaction,
        on_delete=models.PROTECT,
        related_name='ledger_entries',
        help_text="Transaction this entry is part of"
    )
    entry_type = models.CharField(
        max_length=10,
        choices=EntryType.choices,
        help_text="Debit or Credit"
    )
    amount = models.DecimalField(
        max_digits=settings.WALLET_MAX_DIGITS,
        decimal_places=settings.WALLET_DECIMAL_PLACES,
        validators=[MinValueValidator(Decimal('0.01'))],
        help_text="Entry amount (always positive)"
    )
    balance_after = models.DecimalField(
        max_digits=settings.WALLET_MAX_DIGITS,
        decimal_places=settings.WALLET_DECIMAL_PLACES,
        help_text="Cached running balance after this entry"
    )
    description = models.TextField(
        blank=True,
        help_text="Entry description"
    )
    
    class Meta:
        db_table = 'ledger_entries'
        verbose_name = 'Ledger Entry'
        verbose_name_plural = 'Ledger Entries'
        indexes = [
            models.Index(fields=['wallet', '-created_at']),
            models.Index(fields=['transaction']),
            models.Index(fields=['entry_type']),
        ]
        # Ensure entries are ordered consistently for balance calculation
        ordering = ['created_at', 'id']
        
    def __str__(self):
        return f"{self.entry_type}: {self.amount} on {self.wallet}"
    
    def save(self, *args, **kwargs):
        """
        Override save to prevent updates (entries are immutable).
        """
        if self.pk is not None:
            raise ValueError("Ledger entries cannot be modified once created")
        super().save(*args, **kwargs)
    
    def delete(self, *args, **kwargs):
        """
        Override delete to prevent deletion (entries are immutable).
        """
        raise ValueError("Ledger entries cannot be deleted")