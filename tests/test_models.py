"""
Tests for wallet models.
"""
import pytest
from decimal import Decimal
from django.db import IntegrityError
from apps.wallets.models import Wallet, Transaction, LedgerEntry
from apps.wallets.constants import TransactionType, TransactionStatus, EntryType


@pytest.mark.django_db
class TestWalletModel:
    """Tests for Wallet model."""
    
    def test_create_wallet(self, user):
        """Test creating a wallet."""
        wallet = Wallet.objects.create(
            user=user,
            currency='NGN',
            name='My Wallet'
        )
        
        assert wallet.id is not None
        assert wallet.user == user
        assert wallet.currency == 'NGN'
        assert not wallet.is_system
        assert wallet.get_balance() == Decimal('0.00')
    
    def test_create_system_wallet(self):
        """Test creating a system wallet."""
        wallet, created = Wallet.objects.get_or_create(
            is_system=True,
            currency='NGN',
            name='SYSTEM'
        )
        
        assert wallet.is_system
        assert wallet.user is None
        
    def test_unique_user_currency_constraint(self, user):
        """Test that a user can't have duplicate wallets for the same currency."""
        Wallet.objects.create(user=user, currency='NGN', name='Wallet 1')
        
        with pytest.raises(IntegrityError):
            Wallet.objects.create(user=user, currency='NGN', name='Wallet 2')
            
    def test_system_wallet_cannot_have_user(self, user):
        """Test that system wallets cannot have a user."""
        with pytest.raises(IntegrityError):
            Wallet.objects.create(
                user=user,
                is_system=True,
                currency='NGN',
                name='Invalid'
            )
            
    def test_get_balance_empty_wallet(self, wallet):
        """Test getting balance of an empty wallet."""
        assert wallet.get_balance() == Decimal('0.00')
    
    def test_compute_balance_empty_wallet(self, wallet):
        """Test computing balance of an empty wallet."""
        assert wallet.compute_balance() == Decimal('0.00')
        
@pytest.mark.django_db
class TestTransactionModel:
    """Tests for Transaction model."""
    
    def test_create_transaction(self, user):
        """Test creating a transaction."""
        txn = Transaction.objects.create(
            idempotency_key='test-key-123',
            transaction_type=TransactionType.DEPOSIT,
            amount=Decimal('100.00'),
            currency='NGN',
            reference='TXN-001',
            initiated_by=user
        )
        
        assert txn.id is not None
        assert txn.status == TransactionStatus.PENDING
        assert txn.amount == Decimal('100.00')
        
    def test_unique_idempotency_key(self, user):
        """Test that idempotency keys must be unique."""
        Transaction.objects.create(
            idempotency_key='duplicate-key',
            transaction_type=TransactionType.DEPOSIT,
            amount=Decimal('100.00'),
            currency='NGN',
            reference='TXN-001',
            initiated_by=user
        )
        
        with pytest.raises(IntegrityError):
            Transaction.objects.create(
                idempotency_key='duplicate-key',
                transaction_type=TransactionType.DEPOSIT,
                amount=Decimal('200.00'),
                currency='NGN',
                reference='TXN-002',
                initiated_by=user
            )
            
    def test_unique_reference(self, user):
        """Test that transaction references must be unique."""
        Transaction.objects.create(
            idempotency_key='key-1',
            transaction_type=TransactionType.DEPOSIT,
            amount=Decimal('100.00'),
            currency='USD',
            reference='TXN-DUPLICATE',
            initiated_by=user
        )
        
        with pytest.raises(IntegrityError):
            Transaction.objects.create(
                idempotency_key='key-2',
                transaction_type=TransactionType.DEPOSIT,
                amount=Decimal('200.00'),
                currency='USD',
                reference='TXN-DUPLICATE',
                initiated_by=user
            )
            
    def test_create_ledger_entry(self, wallet, user):
        """Test creating a ledger entry."""
        txn = Transaction.objects.create(
            idempotency_key='test-key',
            transaction_type=TransactionType.DEPOSIT,
            amount=Decimal('100.00'),
            currency='NGN',
            reference='TXN-001',
            initiated_by=user
        )
        
        entry = LedgerEntry.objects.create(
            wallet=wallet,
            transaction=txn,
            entry_type=EntryType.CREDIT,
            amount=Decimal('100.00'),
            balance_after=Decimal('100.00'),
            description='Test deposit'
        )
        
        assert entry.id is not None
        assert entry.wallet == wallet
        assert entry.amount == Decimal('100.00')
        
    def test_ledger_entry_immutability(self, wallet, user):
        """Test that ledger entries cannot be modified."""
        txn = Transaction.objects.create(
            idempotency_key='test-key',
            transaction_type=TransactionType.DEPOSIT,
            amount=Decimal('100.00'),
            currency='NGN',
            reference='TXN-001',
            initiated_by=user
        )
        
        entry = LedgerEntry.objects.create(
            wallet=wallet,
            transaction=txn,
            entry_type=EntryType.CREDIT,
            amount=Decimal('100.00'),
            balance_after=Decimal('100.00')
        )
        # Try to update
        entry.amount = Decimal('200.00')
        with pytest.raises(ValueError, match="cannot be modified"):
            entry.save()
            
    def test_ledger_entry_cannot_be_deleted(self, wallet, user):
        """Test that ledger entries cannot be deleted."""
        txn = Transaction.objects.create(
            idempotency_key='test-key',
            transaction_type=TransactionType.DEPOSIT,
            amount=Decimal('100.00'),
            currency='USD',
            reference='TXN-001',
            initiated_by=user
        )
        
        entry = LedgerEntry.objects.create(
            wallet=wallet,
            transaction=txn,
            entry_type=EntryType.CREDIT,
            amount=Decimal('100.00'),
            balance_after=Decimal('100.00')
        )
        
        with pytest.raises(ValueError, match="cannot be deleted"):
            entry.delete()
            
@pytest.mark.django_db
class TestAuditLogModel:
    """Tests for AuditLog model."""
    
    def test_audit_log_immutability(self, user):
        """Test that audit logs cannot be modified."""
        from apps.audit.models import AuditLog
        
        log = AuditLog.objects.create(
            actor=user,
            action='TEST_ACTION',
            metadata={'key': 'value'}
        )
        
        log.action = 'MODIFIED_ACTION'
        with pytest.raises(ValueError, match="cannot be modified"):
            log.save()
    
    def test_audit_log_cannot_be_deleted(self, user):
        """Test that audit logs cannot be deleted."""
        from apps.audit.models import AuditLog
        
        log = AuditLog.objects.create(
            actor=user,
            action='TEST_ACTION',
            metadata={'key': 'value'}
        )
        
        with pytest.raises(ValueError, match="cannot be deleted"):
            log.delete()