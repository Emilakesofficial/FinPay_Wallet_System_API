"""
Integration tests for complete wallet workflows.
"""
import pytest
from decimal import Decimal
from apps.wallets.services import WalletService
from apps.wallets.selectors import WalletSelectors
from apps.wallets.models import Transaction, LedgerEntry
from apps.wallets.constants import TransactionStatus, TransactionType


@pytest.mark.django_db
class TestWalletWorkflows:
    """Test complete wallet workflows."""
    
    def test_complete_user_journey(self, user, another_user):
        """Test a complete user journey: deposit, transfer, withdraw."""
        # User 1 creates wallet and deposits
        wallet1 = WalletSelectors.get_or_create_user_wallet(user)
        
        deposit_txn = WalletService.deposit(
            wallet_id=str(wallet1.id),
            amount=Decimal('1000.00'),
            idempotency_key='journey-deposit-1',
            initiated_by=user,
            description='Initial deposit'
        )
        
        assert deposit_txn.status == TransactionStatus.COMPLETED
        assert wallet1.get_balance() == Decimal('1000.00')
        
        # User 2 creates wallet
        wallet2 = WalletSelectors.get_or_create_user_wallet(another_user)
        assert wallet2.get_balance() == Decimal('0.00')
        
        # User 1 transfers to User 2
        transfer_txn = WalletService.transfer(
            from_wallet_id=str(wallet1.id),
            to_wallet_id=str(wallet2.id),
            amount=Decimal('300.00'),
            idempotency_key='journey-transfer-1',
            initiated_by=user,
            description='Payment to friend'
        )
        
        assert transfer_txn.status == TransactionStatus.COMPLETED
        wallet1.refresh_from_db()
        wallet2.refresh_from_db()
        
        assert wallet1.get_balance() == Decimal('700.00')
        assert wallet2.get_balance() == Decimal('300.00')
        
        # User 1 withdraws
        withdraw_txn = WalletService.withdraw(
            wallet_id=str(wallet1.id),
            amount=Decimal('200.00'),
            idempotency_key='journey-withdraw-1',
            initiated_by=user,
            description='Cash out'
        )
        
        assert withdraw_txn.status == TransactionStatus.COMPLETED
        wallet1.refresh_from_db()
        
        assert wallet1.get_balance() == Decimal('500.00')
        
        # Verify transaction history
        user1_txns = WalletSelectors.get_user_transactions(user)
        assert user1_txns.count() == 3
        
        # Verify ledger entries
        wallet1_statement = WalletSelectors.get_wallet_statement(str(wallet1.id))
        assert wallet1_statement.count() == 3  # 3 transactions = 3 entries for this wallet
    
    def test_money_conservation(self, user, another_user):
        """Test that money is conserved across all operations."""
        from apps.wallets.models import Wallet
        from django.db.models import Sum
        
        # Create wallets
        wallet1 = WalletSelectors.get_or_create_user_wallet(user)
        wallet2 = WalletSelectors.get_or_create_user_wallet(another_user)
        
        # Initial system state: $0
        total_user_money = (
            wallet1.get_balance() + wallet2.get_balance()
        )
        assert total_user_money == Decimal('0.00')
        
        # Deposit $1000 to user 1
        WalletService.deposit(
            wallet_id=str(wallet1.id),
            amount=Decimal('1000.00'),
            idempotency_key='conservation-deposit-1',
            initiated_by=user
        )
        
        # Deposit $500 to user 2
        WalletService.deposit(
            wallet_id=str(wallet2.id),
            amount=Decimal('500.00'),
            idempotency_key='conservation-deposit-2',
            initiated_by=another_user
        )
        
        # Total money should be $1500
        wallet1.refresh_from_db()
        wallet2.refresh_from_db()
        total_user_money = wallet1.get_balance() + wallet2.get_balance()
        assert total_user_money == Decimal('1500.00')
        
        # Transfer $200 from user 1 to user 2
        WalletService.transfer(
            from_wallet_id=str(wallet1.id),
            to_wallet_id=str(wallet2.id),
            amount=Decimal('200.00'),
            idempotency_key='conservation-transfer-1',
            initiated_by=user
        )
        
        # Total money should still be $1500
        wallet1.refresh_from_db()
        wallet2.refresh_from_db()
        total_user_money = wallet1.get_balance() + wallet2.get_balance()
        assert total_user_money == Decimal('1500.00')
        
        # User 1 withdraws $300
        WalletService.withdraw(
            wallet_id=str(wallet1.id),
            amount=Decimal('300.00'),
            idempotency_key='conservation-withdraw-1',
            initiated_by=user
        )
        
        # Total money should now be $1200
        wallet1.refresh_from_db()
        wallet2.refresh_from_db()
        total_user_money = wallet1.get_balance() + wallet2.get_balance()
        assert total_user_money == Decimal('1200.00')
        
        # Verify via double-entry: all debits = all credits
        from django.db.models import Q
        
        totals = LedgerEntry.objects.aggregate(
            total_debits=Sum('amount', filter=Q(entry_type='DEBIT')),
            total_credits=Sum('amount', filter=Q(entry_type='CREDIT'))
        )
        
        assert totals['total_debits'] == totals['total_credits']
    
    def test_balance_accuracy_after_many_operations(self, user):
        """Test that balance remains accurate after many operations."""
        wallet = WalletSelectors.get_or_create_user_wallet(user)
        
        # Perform 100 random operations
        import random
        operations = []
        
        # Initial deposit
        WalletService.deposit(
            wallet_id=str(wallet.id),
            amount=Decimal('10000.00'),
            idempotency_key='accuracy-initial',
            initiated_by=user
        )
        operations.append(('deposit', Decimal('10000.00')))
        
        for i in range(99):
            operation = random.choice(['deposit', 'withdraw'])
            amount = Decimal(str(random.randint(1, 100)))
            
            try:
                if operation == 'deposit':
                    WalletService.deposit(
                        wallet_id=str(wallet.id),
                        amount=amount,
                        idempotency_key=f'accuracy-{i}-deposit',
                        initiated_by=user
                    )
                    operations.append(('deposit', amount))
                else:
                    WalletService.withdraw(
                        wallet_id=str(wallet.id),
                        amount=amount,
                        idempotency_key=f'accuracy-{i}-withdraw',
                        initiated_by=user
                    )
                    operations.append(('withdraw', amount))
            except Exception:
                # Skip if insufficient funds
                pass
        
        # Calculate expected balance
        expected_balance = Decimal('0.00')
        for op, amount in operations:
            if op == 'deposit':
                expected_balance += amount
            else:
                expected_balance -= amount
        
        # Verify balance
        wallet.refresh_from_db()
        actual_balance = wallet.get_balance()
        computed_balance = wallet.compute_balance()
        
        assert actual_balance == expected_balance
        assert computed_balance == expected_balance
        assert actual_balance == computed_balance