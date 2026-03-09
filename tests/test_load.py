"""
Load and concurrency tests for wallet system.
Tests system behavior under high load and concurrent operations.
"""
from django.utils import timezone

import pytest
import threading
import time
from decimal import Decimal
from django.contrib.auth import get_user_model
from apps.wallets.models import Wallet, Transaction, LedgerEntry
from apps.wallets.services import WalletService
from apps.wallets.constants import TransactionStatus
from common.exceptions import InsufficientFundsException
from django.conf import settings

User = get_user_model()


@pytest.fixture(autouse=True, scope='module')
def setup_system_wallet(django_db_blocker):
    """Auto-create system wallet for all tests in this module."""
    with django_db_blocker.unblock():
        Wallet.objects.get_or_create(
            is_system=True,
            currency=settings.WALLET_CURRENCY,
            defaults={'name': 'System Wallet'}
        )

@pytest.mark.django_db(transaction=True)
class TestConcurrentDeposits:
    """Test concurrent deposits to same wallet."""
    
    def test_100_concurrent_deposits(self, user, wallet):
        """Test 100 concurrent deposits to verify no race conditions."""
        num_deposits = 100
        deposit_amount = Decimal('10.00')
        results = []
        errors = []
        
        def deposit_worker(index):
            try:
                from django.db import connection
                connection.ensure_connection()
                
                txn = WalletService.deposit(
                    wallet_id=str(wallet.id),
                    amount=deposit_amount,
                    idempotency_key=f'load-test-deposit-{index}',
                    initiated_by=user
                )
                results.append(txn)
            except Exception as e:
                errors.append((index, str(e)))
            finally:
                connection.close()
        
        # Create and start threads
        threads = []
        start_time = time.time()
        
        for i in range(num_deposits):
            t = threading.Thread(target=deposit_worker, args=(i,))
            threads.append(t)
            t.start()
        
        # Wait for completion
        for t in threads:
            t.join()
        
        duration = time.time() - start_time
        
        # Assertions
        assert len(errors) == 0, f"Errors occurred: {errors}"
        assert len(results) == num_deposits
        
        # Verify final balance
        wallet.refresh_from_db()
        expected_balance = deposit_amount * num_deposits
        actual_balance = wallet.get_balance()
        
        assert actual_balance == expected_balance, \
            f"Expected {expected_balance}, got {actual_balance}"
        
        # Verify computed balance matches
        assert wallet.compute_balance() == expected_balance
        
        # Performance metric
        tps = num_deposits / duration
        print(f"\n✅ Processed {num_deposits} deposits in {duration:.2f}s ({tps:.2f} TPS)")


@pytest.mark.django_db(transaction=True)
class TestConcurrentWithdrawals:
    """Test concurrent withdrawals with balance constraints."""
    
    def test_race_to_empty_wallet(self, user, wallet):
        """
        Test 20 concurrent withdrawals when wallet only has enough for 10.
        Verify exactly 10 succeed and 10 fail with InsufficientFunds.
        """
        # Setup: Deposit $1000 (allows 10 x $100 withdrawals)
        WalletService.deposit(
            wallet_id=str(wallet.id),
            amount=Decimal('1000.00'),
            idempotency_key='load-test-setup',
            initiated_by=user
        )
        
        num_attempts = 20
        withdrawal_amount = Decimal('100.00')
        successful = []
        failed = []
        
        def withdraw_worker(index):
            try:
                from django.db import connection
                connection.ensure_connection()
                
                txn = WalletService.withdraw(
                    wallet_id=str(wallet.id),
                    amount=withdrawal_amount,
                    idempotency_key=f'load-test-withdraw-{index}',
                    initiated_by=user
                )
                successful.append(txn)
            except InsufficientFundsException:
                failed.append(index)
            except Exception as e:
                pytest.fail(f"Unexpected error: {e}")
            finally:
                connection.close()
        
        # Start all threads simultaneously
        threads = []
        for i in range(num_attempts):
            t = threading.Thread(target=withdraw_worker, args=(i,))
            threads.append(t)
        
        for t in threads:
            t.start()
        
        for t in threads:
            t.join()
        
        # Verify results
        assert len(successful) == 10, f"Expected 10 successful, got {len(successful)}"
        assert len(failed) == 10, f"Expected 10 failed, got {len(failed)}"
        
        # Verify final balance is zero
        wallet.refresh_from_db()
        assert wallet.get_balance() == Decimal('0.00')
        
        print(f"\n✅ Correctly handled {num_attempts} concurrent withdrawals")
        print(f"   Successful: {len(successful)}, Failed (insufficient funds): {len(failed)}")


@pytest.mark.django_db(transaction=True)
class TestConcurrentTransfers:
    """Test concurrent transfers between wallets."""
    
    def test_circular_transfers_no_overdraft(self, user, another_user):
        """
        Test circular transfers: A→B, B→A simultaneously.
        Verify no overdrafts occur and money is conserved.
        """
        # Create wallets
        wallet_a = Wallet.objects.create(user=user, currency='NGN', name='Wallet A')
        wallet_b = Wallet.objects.create(user=another_user, currency='NGN', name='Wallet B')
        
        # Setup: Give each $500
        WalletService.deposit(
            wallet_id=str(wallet_a.id),
            amount=Decimal('500.00'),
            idempotency_key='setup-a',
            initiated_by=user
        )
        WalletService.deposit(
            wallet_id=str(wallet_b.id),
            amount=Decimal('500.00'),
            idempotency_key='setup-b',
            initiated_by=another_user
        )
        
        num_transfers = 20
        transfer_amount = Decimal('10.00')
        
        a_to_b_success = []
        b_to_a_success = []
        failures = []
        
        def transfer_a_to_b(index):
            try:
                from django.db import connection
                connection.ensure_connection()
                
                txn = WalletService.transfer(
                    from_wallet_id=str(wallet_a.id),
                    to_wallet_id=str(wallet_b.id),
                    amount=transfer_amount,
                    idempotency_key=f'a-to-b-{index}',
                    initiated_by=user
                )
                a_to_b_success.append(txn)
            except Exception as e:
                failures.append(('A→B', index, str(e)))
            finally:
                connection.close()
        
        def transfer_b_to_a(index):
            try:
                from django.db import connection
                connection.ensure_connection()
                
                txn = WalletService.transfer(
                    from_wallet_id=str(wallet_b.id),
                    to_wallet_id=str(wallet_a.id),
                    amount=transfer_amount,
                    idempotency_key=f'b-to-a-{index}',
                    initiated_by=another_user
                )
                b_to_a_success.append(txn)
            except Exception as e:
                failures.append(('B→A', index, str(e)))
            finally:
                connection.close()
        
        # Create bidirectional transfers
        threads = []
        for i in range(num_transfers):
            t1 = threading.Thread(target=transfer_a_to_b, args=(i,))
            t2 = threading.Thread(target=transfer_b_to_a, args=(i,))
            threads.extend([t1, t2])
        
        # Start all
        for t in threads:
            t.start()
        
        for t in threads:
            t.join()
        
        # Verify no unexpected failures (some InsufficientFunds is OK)
        assert len(failures) == 0 or all('InsufficientFunds' in f[2] for f in failures)
        
        # Verify money conservation
        wallet_a.refresh_from_db()
        wallet_b.refresh_from_db()
        
        final_a = wallet_a.get_balance()
        final_b = wallet_b.get_balance()
        total = final_a + final_b
        
        assert total == Decimal('1000.00'), f"Money not conserved! Total: {total}"
        
        print(f"\n✅ Circular transfers completed")
        print(f"   A→B: {len(a_to_b_success)}, B→A: {len(b_to_a_success)}")
        print(f"   Final A: #{final_a}, Final B: #{final_b}, Total: #{total}")

@pytest.mark.django_db(transaction=True)
def test_deposit_is_atomic_no_partial_ledger(user, wallet, monkeypatch):
    before_entries = LedgerEntry.objects.count()
    before_balance = wallet.compute_balance()

    real_create = LedgerEntry.objects.create
    calls = {"n": 0}

    def flaky_create(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 2:
            raise RuntimeError("boom after first ledger entry")
        return real_create(*args, **kwargs)

    monkeypatch.setattr(LedgerEntry.objects, "create", flaky_create)

    with pytest.raises(Exception):
        WalletService.deposit(
            wallet_id=str(wallet.id),
            amount=Decimal("10.00"),
            idempotency_key="atomicity-test",
            initiated_by=user,
        )

    wallet.refresh_from_db()
    assert LedgerEntry.objects.count() == before_entries
    assert wallet.compute_balance() == before_balance

@pytest.mark.django_db(transaction=True)
def test_completed_txn_has_exactly_two_ledger_entries(user, wallet):
    txn = WalletService.deposit(
        wallet_id=str(wallet.id),
        amount=Decimal("25.00"),
        idempotency_key="two-entries",
        initiated_by=user,
    )

    txn.refresh_from_db()
    assert txn.status == TransactionStatus.COMPLETED
    assert LedgerEntry.objects.filter(transaction=txn).count() == 2

@pytest.mark.django_db(transaction=True)
class TestHighVolumeLoad:
    """Test system under sustained high load."""
    
    def test_1000_sequential_transactions(self, user):
        """Test 1000 sequential transactions for baseline performance."""
        wallet = Wallet.objects.create(user=user, currency='NGN', name='Load Test')
        
        # Initial deposit
        WalletService.deposit(
            wallet_id=str(wallet.id),
            amount=Decimal('10000.00'),
            idempotency_key='bulk-setup',
            initiated_by=user
        )
        
        num_transactions = 1000
        start_time = time.time()
        
        # Alternate deposits and withdrawals
        for i in range(num_transactions):
            if i % 2 == 0:
                WalletService.deposit(
                    wallet_id=str(wallet.id),
                    amount=Decimal('5.00'),
                    idempotency_key=f'bulk-{i}',
                    initiated_by=user
                )
            else:
                WalletService.withdraw(
                    wallet_id=str(wallet.id),
                    amount=Decimal('5.00'),
                    idempotency_key=f'bulk-{i}',
                    initiated_by=user
                )
        
        duration = time.time() - start_time
        tps = num_transactions / duration
        
        # Verify balance is correct (should be back to 10000)
        wallet.refresh_from_db()
        final_balance = wallet.get_balance()
        assert final_balance == Decimal('10000.00')
        
        # Verify transaction count
        completed_count = Transaction.objects.filter(
            status=TransactionStatus.COMPLETED
        ).count()
        assert completed_count == num_transactions + 1  # +1 for setup deposit
        
        print(f"\n✅ Processed {num_transactions} transactions")
        print(f"   Duration: {duration:.2f}s")
        print(f"   Throughput: {tps:.2f} TPS")
        print(f"   Avg latency: {(duration/num_transactions)*1000:.2f}ms")


@pytest.mark.django_db(transaction=True)
class TestIdempotencyUnderLoad:
    """Test idempotency under concurrent requests."""
    
    def test_duplicate_idempotency_keys(self, user, wallet):
        """
        Test 10 threads trying to create same transaction.
        All should succeed but only ONE transaction is created.
        """
        idempotency_key = 'shared-key-test'
        num_threads = 10
        amount = Decimal('100.00')
        
        results = []
        errors = []
        
        def deposit_with_same_key():
            try:
                from django.db import connection
                connection.ensure_connection()
                
                txn = WalletService.deposit(
                    wallet_id=str(wallet.id),
                    amount=amount,
                    idempotency_key=idempotency_key,
                    initiated_by=user
                )
                results.append(txn)
            except Exception as e:
                errors.append(str(e))
            finally:
                connection.close()
        
        # Create threads
        threads = []
        for _ in range(num_threads):
            t = threading.Thread(target=deposit_with_same_key)
            threads.append(t)
        
        for t in threads:
            t.start()
        
        for t in threads:
            t.join()
        
        # All should return a transaction (some get the original, some get duplicate)
        assert len(results) == num_threads
        
        # All should be the SAME transaction
        transaction_ids = set(txn.id for txn in results)
        assert len(transaction_ids) == 1, f"Multiple transactions created: {transaction_ids}"
        
        # Only ONE deposit should have occurred
        wallet.refresh_from_db()
        assert wallet.get_balance() == amount
        
        print(f"\n✅ Idempotency verified: {num_threads} threads, 1 transaction created")
        
@pytest.mark.django_db(transaction=True)
class TestGetBalanceUnderLoad:
    def test_get_balance_matches_computed_under_same_timestamp_load(self, user, monkeypatch):
        """
        Forces MANY ledger entries to share the exact same created_at timestamp.
        If Wallet.get_balance() orders only by '-created_at' (no '-id' tie-break),
        it can return an older balance_after.

        This test should FAIL with:
            order_by('-created_at')
        and PASS with:
            order_by('-created_at', '-id')
        """
        wallet = Wallet.objects.create(user=user, currency="NGN", name="Balance Load Wallet")

        fixed_now = timezone.now()
        monkeypatch.setattr(timezone, "now", lambda: fixed_now)

        n = 200
        amount = Decimal("10.00")

        for i in range(n):
            WalletService.deposit(
                wallet_id=str(wallet.id),
                amount=amount,
                idempotency_key=f"bal-load-{i}",
                initiated_by=user,
            )

        wallet.refresh_from_db()
        expected = amount * n

        cached = wallet.get_balance()
        computed = wallet.compute_balance()

        assert computed == expected
        assert cached == expected, f"get_balance returned {cached} but expected {expected}"
        assert cached == computed

    def test_get_balance_does_not_regress_while_writing(self, user, monkeypatch):
        """
        Writer threads deposit concurrently while a reader polls get_balance().
        With correct ordering, observed balances should be non-decreasing and final correct.
        """
        wallet = Wallet.objects.create(user=user, currency="NGN", name="Polling Wallet")

        fixed_now = timezone.now()
        monkeypatch.setattr(timezone, "now", lambda: fixed_now)

        num_threads = 20
        deposits_per_thread = 25
        amount = Decimal("1.00")
        total_deposits = num_threads * deposits_per_thread
        expected_final = amount * total_deposits

        errors = []
        observed = []
        stop = threading.Event()

        def writer(ti: int):
            try:
                from django.db import connection
                connection.ensure_connection()
                for j in range(deposits_per_thread):
                    WalletService.deposit(
                        wallet_id=str(wallet.id),
                        amount=amount,
                        idempotency_key=f"poll-write-{ti}-{j}",
                        initiated_by=user,
                    )
            except Exception as e:
                errors.append(str(e))
            finally:
                connection.close()

        def reader():
            try:
                from django.db import connection
                connection.ensure_connection()
                while not stop.is_set():
                    wallet.refresh_from_db()
                    observed.append(wallet.get_balance())
                    time.sleep(0.001)
            finally:
                connection.close()

        writers = [threading.Thread(target=writer, args=(i,)) for i in range(num_threads)]
        r = threading.Thread(target=reader)

        r.start()
        for t in writers:
            t.start()
        for t in writers:
            t.join()
        stop.set()
        r.join()

        assert not errors, f"Writer errors: {errors}"

        # final balance correct
        wallet.refresh_from_db()
        assert wallet.get_balance() == expected_final
        assert wallet.compute_balance() == expected_final

        # observed balances should not go backwards (regression indicates non-deterministic "latest" selection)
        # (allow duplicates because reader can sample same value many times)
        assert all(observed[i] <= observed[i + 1] for i in range(len(observed) - 1)), (
            "Observed balance regressed during writes. "
            "This often happens if get_balance() doesn't break ties deterministically "
            "(e.g., missing '-id' in ordering)."
        )