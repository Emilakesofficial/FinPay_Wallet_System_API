"""
Tests for WalletService - the core of the money movement system.
"""
import pytest
import uuid
from decimal import Decimal
from django.db import transaction as db_transaction
from django.db.models import Sum, Q, DecimalField
from apps.wallets.services import WalletService
from apps.wallets.models import Wallet, Transaction, LedgerEntry
from apps.wallets.constants import TransactionStatus, TransactionType, EntryType
from common.exceptions import (
    InsufficientFundsException,
    InvalidAmountException,
    WalletNotFoundException,
    DuplicateTransactionException,
)


@pytest.mark.django_db
class TestWalletServiceDeposit:
    """Tests for deposit operations."""
    
    def test_deposit_success(self, wallet, system_wallet, user):
        """Test successful deposit."""
        initial_balance = wallet.get_balance()
        
        txn = WalletService.deposit(
            wallet_id=str(wallet.id),
            amount=Decimal('100.00'),
            idempotency_key='deposit-test-1',
            initiated_by=user,
            description='Test deposit'
        )
        
        assert txn.status == TransactionStatus.COMPLETED
        assert txn.transaction_type == TransactionType.DEPOSIT
        assert txn.amount == Decimal('100.00')
        
        # Check wallet balance increased
        assert wallet.get_balance() == initial_balance + Decimal('100.00')
        
        # Check ledger entries
        entries = LedgerEntry.objects.filter(transaction=txn)
        assert entries.count() == 2
        
        debit_entry = entries.get(entry_type=EntryType.DEBIT)
        credit_entry = entries.get(entry_type=EntryType.CREDIT)
        
        assert debit_entry.wallet == system_wallet
        assert credit_entry.wallet == wallet
        assert debit_entry.amount == credit_entry.amount == Decimal('100.00')
    
    def test_deposit_idempotency(self, wallet, user):
        """Test that duplicate deposits are prevented."""
        idempotency_key = 'deposit-idempotent-1'
        
        # First deposit
        txn1 = WalletService.deposit(
            wallet_id=str(wallet.id),
            amount=Decimal('100.00'),
            idempotency_key=idempotency_key,
            initiated_by=user
        )
        
        # Second deposit with same key should return the same transaction
        txn2 = WalletService.deposit(
            wallet_id=str(wallet.id),
            amount=Decimal('200.00'),  # Different amount!
            idempotency_key=idempotency_key,
            initiated_by=user
        )
        
        assert txn1.id == txn2.id
        assert txn2.amount == Decimal('100.00')  # Original amount
        wallet.refresh_from_db()
        # Balance should only reflect one deposit
        assert wallet.get_balance() == Decimal('100.00')
    
    def test_deposit_invalid_amount(self, wallet, user):
        """Test deposit with invalid amount."""
        with pytest.raises(InvalidAmountException):
            WalletService.deposit(
                wallet_id=str(wallet.id),
                amount=Decimal('-10.00'),  # Negative
                idempotency_key='deposit-invalid-1',
                initiated_by=user
            )
        
        with pytest.raises(InvalidAmountException):
            WalletService.deposit(
                wallet_id=str(wallet.id),
                amount=Decimal('0.00'),  # Zero
                idempotency_key='deposit-invalid-2',
                initiated_by=user
            )
    
    def test_deposit_wallet_not_found(self, user):
        """Test deposit to non-existent wallet."""
        with pytest.raises(Wallet.DoesNotExist):
            WalletService.deposit(
                wallet_id=str(uuid.uuid4()),
                amount=Decimal('100.00'),
                idempotency_key='deposit-notfound-1',
                initiated_by=user
            )
    
    def test_deposit_balance_consistency(self, wallet, user):
        """Test that cached and computed balances match after deposit."""
        WalletService.deposit(
            wallet_id=str(wallet.id),
            amount=Decimal('123.45'),
            idempotency_key='deposit-consistency-1',
            initiated_by=user
        )
        
        cached_balance = wallet.get_balance()
        computed_balance = wallet.compute_balance()
        
        assert cached_balance == computed_balance == Decimal('123.45')


@pytest.mark.django_db
class TestWalletServiceWithdraw:
    """Tests for withdrawal operations."""
    
    def test_withdraw_success(self, wallet, user):
        """Test successful withdrawal."""
        # First deposit some money
        WalletService.deposit(
            wallet_id=str(wallet.id),
            amount=Decimal('200.00'),
            idempotency_key='withdraw-setup-1',
            initiated_by=user
        )
        
        # Now withdraw
        txn = WalletService.withdraw(
            wallet_id=str(wallet.id),
            amount=Decimal('50.00'),
            idempotency_key='withdraw-test-1',
            initiated_by=user,
            description='Test withdrawal'
        )
        
        assert txn.status == TransactionStatus.COMPLETED
        assert txn.transaction_type == TransactionType.WITHDRAWAL
        assert txn.amount == Decimal('50.00')
        
        # Check wallet balance decreased
        assert wallet.get_balance() == Decimal('150.00')
    
    def test_withdraw_insufficient_funds(self, wallet, user):
        """Test withdrawal with insufficient funds."""
        # Deposit $100
        WalletService.deposit(
            wallet_id=str(wallet.id),
            amount=Decimal('100.00'),
            idempotency_key='withdraw-insufficient-setup',
            initiated_by=user
        )
        
        # Try to withdraw $150
        with pytest.raises(InsufficientFundsException) as exc_info:
            WalletService.withdraw(
                wallet_id=str(wallet.id),
                amount=Decimal('150.00'),
                idempotency_key='withdraw-insufficient-1',
                initiated_by=user
            )
        
        assert 'Insufficient funds' in str(exc_info.value)
        
        # Balance should be unchanged
        assert wallet.get_balance() == Decimal('100.00')
    
    def test_withdraw_exact_balance(self, wallet, user):
        """Test withdrawal of exact balance."""
        # Deposit $100
        WalletService.deposit(
            wallet_id=str(wallet.id),
            amount=Decimal('100.00'),
            idempotency_key='withdraw-exact-setup',
            initiated_by=user
        )
        
        # Withdraw exactly $100
        txn = WalletService.withdraw(
            wallet_id=str(wallet.id),
            amount=Decimal('100.00'),
            idempotency_key='withdraw-exact-1',
            initiated_by=user
        )
        
        assert txn.status == TransactionStatus.COMPLETED
        assert wallet.get_balance() == Decimal('0.00')
    
    def test_withdraw_idempotency(self, wallet, user):
        """Test withdrawal idempotency."""
        # Setup: deposit money
        WalletService.deposit(
            wallet_id=str(wallet.id),
            amount=Decimal('200.00'),
            idempotency_key='withdraw-idemp-setup',
            initiated_by=user
        )
        
        idempotency_key = 'withdraw-idemp-1'
        
        # First withdrawal
        txn1 = WalletService.withdraw(
            wallet_id=str(wallet.id),
            amount=Decimal('50.00'),
            idempotency_key=idempotency_key,
            initiated_by=user
        )
        
        # Second withdrawal with same key
        txn2 = WalletService.withdraw(
            wallet_id=str(wallet.id),
            amount=Decimal('100.00'),  # Different amount
            idempotency_key=idempotency_key,
            initiated_by=user
        )
        
        assert txn1.id == txn2.id
        
        # Balance should only reflect one withdrawal
        assert wallet.get_balance() == Decimal('150.00')


@pytest.mark.django_db
class TestWalletServiceTransfer:
    """Tests for transfer operations."""
    
    def test_transfer_success(self, wallet, another_wallet, user):
        """Test successful transfer."""
        # Setup: deposit to sender
        WalletService.deposit(
            wallet_id=str(wallet.id),
            amount=Decimal('500.00'),
            idempotency_key='transfer-setup-1',
            initiated_by=user
        )
        
        sender_initial = wallet.get_balance()
        receiver_initial = another_wallet.get_balance()
        
        # Transfer
        txn = WalletService.transfer(
            from_wallet_id=str(wallet.id),
            to_wallet_id=str(another_wallet.id),
            amount=Decimal('150.00'),
            idempotency_key='transfer-test-1',
            initiated_by=user,
            description='Test transfer'
        )
        
        assert txn.status == TransactionStatus.COMPLETED
        assert txn.transaction_type == TransactionType.TRANSFER
        assert txn.amount == Decimal('150.00')
        
        # Refresh from DB
        wallet.refresh_from_db()
        another_wallet.refresh_from_db()
        
        # Check balances
        assert wallet.get_balance() == sender_initial - Decimal('150.00')
        assert another_wallet.get_balance() == receiver_initial + Decimal('150.00')
        
        # Check ledger entries
        entries = LedgerEntry.objects.filter(transaction=txn)
        assert entries.count() == 2
        
        debit_entry = entries.get(entry_type=EntryType.DEBIT)
        credit_entry = entries.get(entry_type=EntryType.CREDIT)
        
        assert debit_entry.wallet == wallet
        assert credit_entry.wallet == another_wallet
    
    def test_transfer_insufficient_funds(self, wallet, another_wallet, user):
        """Test transfer with insufficient funds."""
        # Deposit only $50
        WalletService.deposit(
            wallet_id=str(wallet.id),
            amount=Decimal('50.00'),
            idempotency_key='transfer-insufficient-setup',
            initiated_by=user
        )
        
        # Try to transfer $100
        with pytest.raises(InsufficientFundsException):
            WalletService.transfer(
                from_wallet_id=str(wallet.id),
                to_wallet_id=str(another_wallet.id),
                amount=Decimal('100.00'),
                idempotency_key='transfer-insufficient-1',
                initiated_by=user
            )
    
    def test_transfer_to_same_wallet(self, wallet, user):
        """Test that transfer to same wallet is rejected."""
        with pytest.raises(InvalidAmountException, match='same wallet'):
            WalletService.transfer(
                from_wallet_id=str(wallet.id),
                to_wallet_id=str(wallet.id),
                amount=Decimal('100.00'),
                idempotency_key='transfer-same-1',
                initiated_by=user
            )
    
    def test_transfer_idempotency(self, wallet, another_wallet, user):
        """Test transfer idempotency."""
        # Setup
        WalletService.deposit(
            wallet_id=str(wallet.id),
            amount=Decimal('500.00'),
            idempotency_key='transfer-idemp-setup',
            initiated_by=user
        )
        
        idempotency_key = 'transfer-idemp-1'
        
        # First transfer
        txn1 = WalletService.transfer(
            from_wallet_id=str(wallet.id),
            to_wallet_id=str(another_wallet.id),
            amount=Decimal('100.00'),
            idempotency_key=idempotency_key,
            initiated_by=user
        )
        
        # Second transfer with same key
        txn2 = WalletService.transfer(
            from_wallet_id=str(wallet.id),
            to_wallet_id=str(another_wallet.id),
            amount=Decimal('200.00'),  # Different amount
            idempotency_key=idempotency_key,
            initiated_by=user
        )
        
        assert txn1.id == txn2.id
        
        # Balances should only reflect one transfer
        wallet.refresh_from_db()
        another_wallet.refresh_from_db()
        
        assert wallet.get_balance() == Decimal('400.00')
        assert another_wallet.get_balance() == Decimal('100.00')
    
    def test_transfer_wallet_not_found(self, wallet, user):
        """Test transfer with non-existent wallet."""
        fake_wallet_id = str(uuid.uuid4())
        
        with pytest.raises(WalletNotFoundException):
            WalletService.transfer(
                from_wallet_id=str(wallet.id),
                to_wallet_id=fake_wallet_id,
                amount=Decimal('100.00'),
                idempotency_key='transfer-notfound-1',
                initiated_by=user
            )


@pytest.mark.django_db
class TestWalletServiceBalance:
    """Tests for balance operations."""
    
    def test_get_balance_empty_wallet(self, wallet):
        """Test getting balance of empty wallet."""
        balance_info = WalletService.get_balance(str(wallet.id))
        
        assert balance_info['balance'] == '0.00'
        assert balance_info['computed_balance'] == '0.00'
        assert balance_info['is_consistent'] is True
    
    def test_get_balance_after_operations(self, wallet, another_wallet, user):
        """Test balance after various operations."""
        # Deposit
        WalletService.deposit(
            wallet_id=str(wallet.id),
            amount=Decimal('1000.00'),
            idempotency_key='balance-test-1',
            initiated_by=user
        )
        
        # Withdraw
        WalletService.withdraw(
            wallet_id=str(wallet.id),
            amount=Decimal('250.00'),
            idempotency_key='balance-test-2',
            initiated_by=user
        )
        
        # Transfer
        WalletService.transfer(
            from_wallet_id=str(wallet.id),
            to_wallet_id=str(another_wallet.id),
            amount=Decimal('150.00'),
            idempotency_key='balance-test-3',
            initiated_by=user
        )
        
        balance_info = WalletService.get_balance(str(wallet.id))
        
        # 1000 - 250 - 150 = 600
        assert balance_info['balance'] == '600.00'
        assert balance_info['computed_balance'] == '600.00'
        assert balance_info['is_consistent'] is True
    
    def test_get_balance_wallet_not_found(self):
        """Test getting balance of non-existent wallet."""
        with pytest.raises(WalletNotFoundException):
            WalletService.get_balance(str(uuid.uuid4()))


@pytest.mark.django_db
class TestDoubleEntryBookkeeping:
    """Tests to verify double-entry bookkeeping principles."""
    
    def test_every_transaction_has_two_entries(self, wallet, user):
        """Test that every completed transaction has exactly 2 ledger entries."""
        txn = WalletService.deposit(
            wallet_id=str(wallet.id),
            amount=Decimal('100.00'),
            idempotency_key='double-entry-1',
            initiated_by=user
        )
        
        entries = LedgerEntry.objects.filter(transaction=txn)
        assert entries.count() == 2
        
        debit_entries = entries.filter(entry_type=EntryType.DEBIT)
        credit_entries = entries.filter(entry_type=EntryType.CREDIT)
        
        assert debit_entries.count() == 1
        assert credit_entries.count() == 1
    
    def test_debits_equal_credits(self, wallet, another_wallet, user):
        """Test that total debits equal total credits for any transaction."""
        # Perform various operations
        WalletService.deposit(
            wallet_id=str(wallet.id),
            amount=Decimal('500.00'),
            idempotency_key='de-test-1',
            initiated_by=user
        )
        
        WalletService.withdraw(
            wallet_id=str(wallet.id),
            amount=Decimal('100.00'),
            idempotency_key='de-test-2',
            initiated_by=user
        )
        
        WalletService.transfer(
            from_wallet_id=str(wallet.id),
            to_wallet_id=str(another_wallet.id),
            amount=Decimal('150.00'),
            idempotency_key='de-test-3',
            initiated_by=user
        )
        
        # For each transaction, sum of debits should equal sum of credits
        transactions = Transaction.objects.filter(status=TransactionStatus.COMPLETED)
        
        for txn in transactions:
            entries = LedgerEntry.objects.filter(transaction=txn)
            
            total_debits = sum(
                e.amount for e in entries if e.entry_type == EntryType.DEBIT
            )
            total_credits = sum(
                e.amount for e in entries if e.entry_type == EntryType.CREDIT
            )
            
            assert total_debits == total_credits
    
    def test_system_balance_is_zero(self, wallet, another_wallet, user, system_wallet):
        """Test that system-wide debits equal credits (the books balance)."""
        # Perform various operations
        WalletService.deposit(
            wallet_id=str(wallet.id),
            amount=Decimal('1000.00'),
            idempotency_key='system-balance-1',
            initiated_by=user
        )
        
        WalletService.deposit(
            wallet_id=str(another_wallet.id),
            amount=Decimal('500.00'),
            idempotency_key='system-balance-2',
            initiated_by=user
        )
        
        WalletService.transfer(
            from_wallet_id=str(wallet.id),
            to_wallet_id=str(another_wallet.id),
            amount=Decimal('200.00'),
            idempotency_key='system-balance-3',
            initiated_by=user
        )
        
        # Sum all debits and credits across the entire system
        from django.db.models import Sum
        
        totals = LedgerEntry.objects.aggregate(
            total_debits=Sum('amount', filter=Q(entry_type=EntryType.DEBIT)),
            total_credits=Sum('amount', filter=Q(entry_type=EntryType.CREDIT))
        )
        
        assert totals['total_debits'] == totals['total_credits']