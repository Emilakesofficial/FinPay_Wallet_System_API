"""
Selector layer for read-only wallet queries.

Separates reads from writes for clarity and potential performance optimization.
"""
import logging
from typing import List, Optional
from django.db.models import QuerySet, Q, Sum, Count
from django.contrib.auth import get_user_model

from .models import Wallet, Transaction, LedgerEntry
from .constants import TransactionStatus, TransactionType
from common.exceptions import WalletNotFoundException

User = get_user_model()
logger = logging.getLogger(__name__)


class WalletSelectors:
    """Read-only queries for wallet data."""
    
    @staticmethod
    def get_user_wallet(user: User, currency: str = 'NGN') -> Wallet:
        """
        Get a user's wallet for a specific currency.
        
        Args:
            user: The user
            currency: Currency code
        
        Returns:
            Wallet: User's wallet
        
        Raises:
            WalletNotFoundException: If wallet not found
        """
        try:
            return Wallet.objects.get(user=user, currency=currency)
        except Wallet.DoesNotExist:
            logger.error(f"Wallet not found for user {user.id}, currency {currency}")
            raise WalletNotFoundException(
                f"Wallet not found for user {user.email} with currency {currency}"
            )
    
    @staticmethod
    def get_or_create_user_wallet(user: User, currency: str = 'NGN') -> Wallet:
        """
        Get or create a user's wallet.
        
        Args:
            user: The user
            currency: Currency code
        
        Returns:
            Wallet: User's wallet
        """
        wallet, created = Wallet.objects.get_or_create(
            user=user,
            currency=currency,
            defaults={
                'name': f"{user.email}'s {currency} Wallet"
            }
        )
        
        if created:
            logger.info(f"Created new wallet for user {user.id}: {wallet.id}")
        
        return wallet
    
    @staticmethod
    def get_wallet_statement(
        wallet_id: str,
        limit: int = 50,
        offset: int = 0
    ) -> QuerySet[LedgerEntry]:
        """
        Get ledger entries (statement) for a wallet.
        
        Args:
            wallet_id: UUID of the wallet
            limit: Number of entries to return
            offset: Offset for pagination
        
        Returns:
            QuerySet: Ledger entries
        """
        return LedgerEntry.objects.filter(
            wallet_id=wallet_id
        ).select_related(
            'transaction'
        ).order_by(
            '-created_at'
        )[offset:offset + limit]
    
    @staticmethod
    def get_user_transactions(
        user: User,
        transaction_type: Optional[TransactionType] = None,
        status: Optional[TransactionStatus] = None,
        limit: int = 50,
        offset: int = 0
    ) -> QuerySet[Transaction]:
        """
        Get transactions for a user.
        
        Args:
            user: The user
            transaction_type: Filter by transaction type
            status: Filter by status
            limit: Number of transactions to return
            offset: Offset for pagination
        
        Returns:
            QuerySet: Transactions
        """
        # Get user's wallet IDs
        wallet_ids = Wallet.objects.filter(user=user).values_list('id', flat=True)
        
        # Build query
        query = Q(ledger_entries__wallet_id__in=wallet_ids)
        
        if transaction_type:
            query &= Q(transaction_type=transaction_type)
        
        if status:
            query &= Q(status=status)
        
        return Transaction.objects.filter(
            query
        ).distinct().order_by(
            '-created_at'
        )[offset:offset + limit]
    
    @staticmethod
    def get_wallet_statistics(wallet_id: str) -> dict:
        """
        Get statistics for a wallet.
        
        Args:
            wallet_id: UUID of the wallet
        
        Returns:
            dict: Statistics
        """
        from django.db.models import Sum, Count
        from decimal import Decimal
        
        stats = LedgerEntry.objects.filter(
            wallet_id=wallet_id
        ).aggregate(
            total_entries=Count('id'),
            total_debits=Sum('amount', filter=Q(entry_type='DEBIT')) or Decimal('0'),
            total_credits=Sum('amount', filter=Q(entry_type='CREDIT')) or Decimal('0'),
        )
        
        transaction_stats = Transaction.objects.filter(
            ledger_entries__wallet_id=wallet_id
        ).values('transaction_type').annotate(
            count=Count('id')
        )
        
        return {
            'total_entries': stats['total_entries'],
            'total_debits': str(stats['total_debits']),
            'total_credits': str(stats['total_credits']),
            'transactions_by_type': {
                item['transaction_type']: item['count'] 
                for item in transaction_stats
            }
        }