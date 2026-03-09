"""
Concurrency tests to ensure thread-safety of wallet operations.

These tests simulate real-world scenarios where multiple requests
hit the same wallet simultaneously.
"""
import pytest
import threading
from decimal import Decimal
from django.db import connection
from apps.wallets.services import WalletService
from apps.wallets.models import Wallet
from common.exceptions import InsufficientFundsException, DuplicateTransactionException


@pytest.mark.django_db(transaction=True)
class TestConcurrency:
    """Tests for concurrent operations."""
    
    def test_concurrent_deposits(self,system_wallet, wallet, user):
        """Test that concurrent deposits don't cause balance inconsistencies."""
        num_threads = 10
        deposit_amount = Decimal('10.00')
        results = []
        errors = []
        
        def deposit():
            """Thread worker function."""
            try:
                # Each thread needs its own database connection
                from django.db import connection
                connection.ensure_connection()
                
                idempotency_key = f'concurrent-deposit-{threading.current_thread().name}'
                txn = WalletService.deposit(
                    wallet_id=str(wallet.id),
                    amount=deposit_amount,
                    idempotency_key=idempotency_key,
                    initiated_by=user
                )
                results.append(txn)
            except Exception as e:
                errors.append(e)
            finally:
                connection.close()
        
        # Create and start threads
        threads = []
        for i in range(num_threads):
            t = threading.Thread(target=deposit, name=f'thread-{i}')
            threads.append(t)
            t.start()
        
        # Wait for all threads to complete
        for t in threads:
            t.join()
        
        # Verify no errors
        assert len(errors) == 0, f"Errors occurred: {errors}"
        
        # Verify all deposits succeeded
        assert len(results) == num_threads
        
        # Verify final balance
        wallet.refresh_from_db()
        expected_balance = deposit_amount * num_threads
        assert wallet.get_balance() == expected_balance
        
        # Verify computed balance matches
        assert wallet.compute_balance() == expected_balance
    
    def test_concurrent_withdrawals_insufficient_funds(self, system_wallet, wallet, user):
        """Test that concurrent withdrawals properly handle insufficient funds."""
        # Setup: deposit $100
        WalletService.deposit(
            wallet_id=str(wallet.id),
            amount=Decimal('100.00'),
            idempotency_key='concurrent-withdraw-setup',
            initiated_by=user
        )
        
        num_threads = 10
        withdraw_amount = Decimal('20.00')  # Each wants to withdraw $20
        successful_withdrawals = []
        failed_withdrawals = []
        
        def withdraw():
            """Thread worker function."""
            try:
                from django.db import connection
                connection.ensure_connection()
                
                idempotency_key = f'concurrent-withdraw-{threading.current_thread().name}'
                txn = WalletService.withdraw(
                    wallet_id=str(wallet.id),
                    amount=withdraw_amount,
                    idempotency_key=idempotency_key,
                    initiated_by=user
                )
                successful_withdrawals.append(txn)
            except InsufficientFundsException:
                failed_withdrawals.append(threading.current_thread().name)
            finally:
                connection.close()
        
        # Create and start threads
        threads = []
        for i in range(num_threads):
            t = threading.Thread(target=withdraw, name=f'thread-{i}')
            threads.append(t)
            t.start()
        
        # Wait for all threads
        for t in threads:
            t.join()
        
        # Only 5 withdrawals should succeed ($100 / $20 = 5)
        assert len(successful_withdrawals) == 5
        assert len(failed_withdrawals) == 5
        
        # Final balance should be $0
        wallet.refresh_from_db()
        assert wallet.get_balance() == Decimal('0.00')
    
    def test_concurrent_transfers_no_overdraft(self, system_wallet, wallet, another_wallet, user):
        """Test that concurrent transfers don't allow overdrafts."""
        # Setup: deposit $100 to sender
        WalletService.deposit(
            wallet_id=str(wallet.id),
            amount=Decimal('100.00'),
            idempotency_key='concurrent-transfer-setup',
            initiated_by=user
        )
        
        num_threads = 10
        transfer_amount = Decimal('15.00')
        successful_transfers = []
        failed_transfers = []
        
        def transfer():
            """Thread worker function."""
            try:
                from django.db import connection
                connection.ensure_connection()
                
                idempotency_key = f'concurrent-transfer-{threading.current_thread().name}'
                txn = WalletService.transfer(
                    from_wallet_id=str(wallet.id),
                    to_wallet_id=str(another_wallet.id),
                    amount=transfer_amount,
                    idempotency_key=idempotency_key,
                    initiated_by=user
                )
                successful_transfers.append(txn)
            except InsufficientFundsException:
                failed_transfers.append(threading.current_thread().name)
            finally:
                connection.close()
        
        # Create and start threads
        threads = []
        for i in range(num_threads):
            t = threading.Thread(target=transfer, name=f'thread-{i}')
            threads.append(t)
            t.start()
        
        # Wait for all threads
        for t in threads:
            t.join()
        
        # Only 6 transfers should succeed ($100 / $15 = 6 with $10 remainder)
        assert len(successful_transfers) == 6
        assert len(failed_transfers) == 4
        
        # Verify balances
        wallet.refresh_from_db()
        another_wallet.refresh_from_db()
        
        sender_balance = wallet.get_balance()
        receiver_balance = another_wallet.get_balance()
        
        # Sender should have $10 left (100 - 6*15 = 10)
        assert sender_balance == Decimal('10.00')
        
        # Receiver should have $90 (6*15 = 90)
        assert receiver_balance == Decimal('90.00')
        
        # Total money in system should be conserved
        assert sender_balance + receiver_balance == Decimal('100.00')
    
    def test_idempotency_under_concurrency(self, system_wallet, wallet, user):
        """Test that idempotency works correctly under concurrent requests."""
        num_threads = 5
        idempotency_key = 'shared-idempotency-key'
        deposit_amount = Decimal('100.00')
        
        results = []
        duplicate_errors = []
        
        def deposit():
            """Thread worker function."""
            try:
                from django.db import connection
                connection.ensure_connection()
                
                txn = WalletService.deposit(
                    wallet_id=str(wallet.id),
                    amount=deposit_amount,
                    idempotency_key=idempotency_key,
                    initiated_by=user
                )
                results.append(txn)
            except DuplicateTransactionException as e:
                duplicate_errors.append(e)
            finally:
                connection.close()
        
        # Create and start threads with same idempotency key
        threads = []
        for i in range(num_threads):
            t = threading.Thread(target=deposit)
            threads.append(t)
            t.start()
        
        # Wait for all threads
        for t in threads:
            t.join()
        
        # All should succeed (some will get the original, some duplicates)
        # But they should all return the same transaction
        assert len(results) >= 1
        
        # All returned transactions should have the same ID
        transaction_ids = {str(txn.id) for txn in results}
        assert len(transaction_ids) == 1
        
        # Balance should only reflect ONE deposit
        wallet.refresh_from_db()
        assert wallet.get_balance() == deposit_amount
    
    def test_deadlock_prevention_in_transfers(self,system_wallet, wallet, another_wallet, user):
        """Test that concurrent bidirectional transfers don't cause deadlocks."""
        # Setup: give each wallet $500
        WalletService.deposit(
            wallet_id=str(wallet.id),
            amount=Decimal('500.00'),
            idempotency_key='deadlock-setup-1',
            initiated_by=user
        )
        
        WalletService.deposit(
            wallet_id=str(another_wallet.id),
            amount=Decimal('500.00'),
            idempotency_key='deadlock-setup-2',
            initiated_by=user
        )
        
        num_pairs = 5
        transfer_amount = Decimal('10.00')
        results = []
        errors = []
        
        def transfer_a_to_b(index):
            """Transfer from wallet to another_wallet."""
            try:
                from django.db import connection
                connection.ensure_connection()
                
                txn = WalletService.transfer(
                    from_wallet_id=str(wallet.id),
                    to_wallet_id=str(another_wallet.id),
                    amount=transfer_amount,
                    idempotency_key=f'deadlock-a-to-b-{index}',
                    initiated_by=user
                )
                results.append(('A->B', txn))
            except Exception as e:
                errors.append(('A->B', e))
            finally:
                connection.close()
        
        def transfer_b_to_a(index):
            """Transfer from another_wallet to wallet."""
            try:
                from django.db import connection
                connection.ensure_connection()
                
                txn = WalletService.transfer(
                    from_wallet_id=str(another_wallet.id),
                    to_wallet_id=str(wallet.id),
                    amount=transfer_amount,
                    idempotency_key=f'deadlock-b-to-a-{index}',
                    initiated_by=user
                )
                results.append(('B->A', txn))
            except Exception as e:
                errors.append(('B->A', e))
            finally:
                connection.close()
        
        # Create threads that transfer in both directions simultaneously
        threads = []
        for i in range(num_pairs):
            t1 = threading.Thread(target=transfer_a_to_b, args=(i,))
            t2 = threading.Thread(target=transfer_b_to_a, args=(i,))
            threads.extend([t1, t2])
        
        # Start all threads
        for t in threads:
            t.start()
        
        # Wait for all threads
        for t in threads:
            t.join()
        
        # Should not have any deadlock errors
        assert len(errors) == 0, f"Errors occurred: {errors}"
        
        # All transfers should succeed
        assert len(results) == num_pairs * 2
        
        # Net effect: balances should be the same (equal transfers in both directions)
        wallet.refresh_from_db()
        another_wallet.refresh_from_db()
        
        assert wallet.get_balance() == Decimal('500.00')
        assert another_wallet.get_balance() == Decimal('500.00')