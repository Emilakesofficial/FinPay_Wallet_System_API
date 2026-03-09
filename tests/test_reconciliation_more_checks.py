from decimal import Decimal
from datetime import timedelta
from django.utils import timezone


def _create_user_and_wallet(unique_prefix):
    from django.conf import settings
    from django.contrib.auth import get_user_model
    from apps.wallets.models import Wallet

    User = get_user_model()
    user = User.objects.create_user(email=f'user+{unique_prefix}@example.com', username=f'user{unique_prefix}', password='pass')

    system_wallet, _ = Wallet.objects.get_or_create(
        is_system=True,
        currency=settings.WALLET_CURRENCY,
        defaults={'name': 'SYSTEM'}
    )
    user_wallet = Wallet.objects.create(user=user, is_system=False, currency=settings.WALLET_CURRENCY, name=f'W-{unique_prefix}')
    return user, system_wallet, user_wallet


def test_check_negative_balances_detects_negative(db):
    """check_negative_balances should find wallets with negative balances."""
    from apps.reconciliation import tasks
    from apps.reconciliation.models import ReconciliationReport
    from apps.wallets.models import Transaction, LedgerEntry
    from apps.wallets.constants import EntryType, TransactionType, TransactionStatus

    user, system_wallet, user_wallet = _create_user_and_wallet('neg')

    # Create a transaction that results in negative balance for user_wallet
    txn = Transaction.objects.create(
        idempotency_key=f'neg-{user.id}',
        transaction_type=TransactionType.TRANSFER,
        status=TransactionStatus.COMPLETED,
        amount=Decimal('200.00'),
        currency=user_wallet.currency,
        reference=f'NEG-{user.id}',
        initiated_by=user,
    )

    # Debit user_wallet (200) without corresponding credit -> negative
    LedgerEntry.objects.create(
        wallet=user_wallet,
        transaction=txn,
        entry_type=EntryType.DEBIT,
        amount=Decimal('200.00'),
        balance_after=Decimal('-200.00'),
        description='forced debit'
    )

    # Create a small credit elsewhere to avoid system-wide imbalance tests failing here
    LedgerEntry.objects.create(
        wallet=system_wallet,
        transaction=txn,
        entry_type=EntryType.CREDIT,
        amount=Decimal('50.00'),
        balance_after=Decimal('50.00'),
        description='partial credit'
    )

    report = ReconciliationReport.objects.create()
    res = tasks.check_negative_balances.apply(args=(str(report.id),))
    result = res.get(timeout=10)

    assert result['check'] == 'negative_balances'
    assert result['passed'] is False
    assert any(d.get('wallet_id') == str(user_wallet.id) for d in result['discrepancies'])


def test_check_transaction_state_flags_issues(db):
    """check_transaction_state should flag failed-with-entries, stuck pending, and wrong entry counts."""
    from apps.reconciliation import tasks
    from apps.reconciliation.models import ReconciliationReport
    from apps.wallets.models import Transaction, LedgerEntry
    from apps.wallets.constants import EntryType, TransactionType, TransactionStatus

    user, system_wallet, user_wallet = _create_user_and_wallet('txn')

    # 1) FAILED transaction with entries
    txn_failed = Transaction.objects.create(
        idempotency_key=f'fail-{user.id}',
        transaction_type=TransactionType.WITHDRAWAL,
        status=TransactionStatus.FAILED,
        amount=Decimal('10.00'),
        currency=user_wallet.currency,
        reference=f'FAIL-{user.id}',
        initiated_by=user,
    )
    LedgerEntry.objects.create(
        wallet=user_wallet,
        transaction=txn_failed,
        entry_type=EntryType.DEBIT,
        amount=Decimal('10.00'),
        balance_after=Decimal('0.00'),
        description='failed debit'
    )

    # 2) PENDING transaction older than 5 minutes
    txn_pending = Transaction.objects.create(
        idempotency_key=f'pend-{user.id}',
        transaction_type=TransactionType.TRANSFER,
        status=TransactionStatus.PENDING,
        amount=Decimal('5.00'),
        currency=user_wallet.currency,
        reference=f'PEND-{user.id}',
        initiated_by=user,
    )
    # set created_at to older than 5 minutes
    old_time = timezone.now() - timedelta(minutes=10)
    Transaction.objects.filter(id=txn_pending.id).update(created_at=old_time)

    # 3) COMPLETED transaction with wrong entry count (only 1)
    txn_bad = Transaction.objects.create(
        idempotency_key=f'bad-{user.id}',
        transaction_type=TransactionType.TRANSFER,
        status=TransactionStatus.COMPLETED,
        amount=Decimal('7.00'),
        currency=user_wallet.currency,
        reference=f'BAD-{user.id}',
        initiated_by=user,
    )
    LedgerEntry.objects.create(
        wallet=user_wallet,
        transaction=txn_bad,
        entry_type=EntryType.DEBIT,
        amount=Decimal('7.00'),
        balance_after=Decimal('0.00'),
        description='single entry'
    )

    report = ReconciliationReport.objects.create()
    res = tasks.check_transaction_state.apply(args=(str(report.id),))
    result = res.get(timeout=10)

    assert result['check'] == 'transaction_state'
    assert result['passed'] is False
    issues = [d.get('issue') for d in result['discrepancies']]
    assert 'FAILED_WITH_ENTRIES' in issues
    assert 'STUCK_PENDING' in issues
    assert 'WRONG_ENTRY_COUNT' in issues


def test_check_global_balance_detects_imbalance(db):
    """check_global_balance should detect when total debits != total credits."""
    from apps.reconciliation import tasks
    from apps.reconciliation.models import ReconciliationReport
    from apps.wallets.models import Transaction, LedgerEntry
    from apps.wallets.constants import EntryType, TransactionType, TransactionStatus

    user, system_wallet, user_wallet = _create_user_and_wallet('glob')

    # Create a transaction with a single debit entry (unbalanced)
    txn = Transaction.objects.create(
        idempotency_key=f'glob-{user.id}',
        transaction_type=TransactionType.WITHDRAWAL,
        status=TransactionStatus.COMPLETED,
        amount=Decimal('33.00'),
        currency=user_wallet.currency,
        reference=f'GLOB-{user.id}',
        initiated_by=user,
    )
    LedgerEntry.objects.create(
        wallet=user_wallet,
        transaction=txn,
        entry_type=EntryType.DEBIT,
        amount=Decimal('33.00'),
        balance_after=Decimal('-33.00'),
        description='unbalanced debit'
    )

    report = ReconciliationReport.objects.create()
    res = tasks.check_global_balance.apply(args=(str(report.id),))
    result = res.get(timeout=10)

    assert result['check'] == 'global_balance'
    assert result['passed'] is False
    assert result['issues_count'] >= 1
