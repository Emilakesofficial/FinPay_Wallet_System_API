from decimal import Decimal


def _create_wallet_and_entries(db, django_user_model):
    """Helper to create a user wallet, system wallet, a transaction and ledger entries."""
    from django.conf import settings
    from apps.wallets.models import Wallet, Transaction, LedgerEntry
    from apps.wallets.constants import EntryType, TransactionType, TransactionStatus
    from django.contrib.auth import get_user_model
    import uuid

    User = get_user_model()
    suffix = str(uuid.uuid4())[:8]
    user = User.objects.create_user(email=f'alice+{suffix}@example.com', username=f'alice{suffix}', password='pass')

    # Create wallets (use get_or_create for system wallet to avoid unique constraint errors)
    system_wallet, _ = Wallet.objects.get_or_create(
        is_system=True,
        currency=settings.WALLET_CURRENCY,
        defaults={'name': 'SYSTEM'}
    )
    user_wallet = Wallet.objects.create(user=user, is_system=False, currency=settings.WALLET_CURRENCY, name='Alice')

    # Create a completed transaction and corresponding ledger entries
    # Ensure unique idempotency_key and reference to avoid test DB collisions
    unique = suffix
    txn = Transaction.objects.create(
        idempotency_key=f'tx-{unique}',
        transaction_type=TransactionType.DEPOSIT,
        status=TransactionStatus.COMPLETED,
        amount=Decimal('100.00'),
        currency=settings.WALLET_CURRENCY,
        reference=f'TEST-REF-{unique}',
        description='Initial deposit',
        initiated_by=user
    )

    # Credit user wallet (amount 100) with correct computed balance
    LedgerEntry.objects.create(
        wallet=user_wallet,
        transaction=txn,
        entry_type=EntryType.CREDIT,
        amount=Decimal('100.00'),
        balance_after=Decimal('100.00'),
        description='Credit'
    )

    # Create system debit entry
    LedgerEntry.objects.create(
        wallet=system_wallet,
        transaction=txn,
        entry_type=EntryType.DEBIT,
        amount=Decimal('100.00'),
        balance_after=Decimal('0.00'),
        description='System debit'
    )

    return user_wallet


def test_check_balance_drift_auto_fix(db, django_user_model, monkeypatch):
    """Small balance drift should be auto-fixed by `check_balance_drift`."""
    from apps.reconciliation import tasks
    from apps.reconciliation.models import ReconciliationReport
    from apps.wallets.models import LedgerEntry
    from decimal import Decimal

    wallet = _create_wallet_and_entries(db, django_user_model)

    # Make the wallet.get_balance return a value slightly off by 0.01
    computed = wallet.compute_balance()
    monkeypatch.setattr(type(wallet), 'get_balance', lambda self: computed - Decimal('0.01'))

    report = ReconciliationReport.objects.create()
    res = tasks.check_balance_drift.apply(args=(str(report.id),))
    result = res.get(timeout=10)

    # Expect passed True if only auto-fixes were applied (no remaining discrepancies)
    assert result['check'] == 'balance_drift'
    assert result['passed'] is True
    assert result['metadata']['auto_fixed'] >= 1

    # Verify latest ledger entry balance_after equals computed
    latest = LedgerEntry.objects.filter(wallet=wallet).order_by('-created_at').first()
    assert latest.balance_after == computed


def test_check_balance_drift_detects_large_drift(db, django_user_model, monkeypatch):
    """Large balance drift should be reported as a discrepancy."""
    from apps.reconciliation import tasks
    from apps.reconciliation.models import ReconciliationReport
    from decimal import Decimal

    wallet = _create_wallet_and_entries(db, django_user_model)

    # Make the wallet.get_balance return a value off by 10.00 (too large to auto-fix)
    computed = wallet.compute_balance()
    monkeypatch.setattr(type(wallet), 'get_balance', lambda self: computed - Decimal('10.00'))

    report = ReconciliationReport.objects.create()
    res = tasks.check_balance_drift.apply(args=(str(report.id),))
    result = res.get(timeout=10)

    assert result['check'] == 'balance_drift'
    assert result['passed'] is False
    # Should include at least one discrepancy for our wallet
    assert any(d.get('wallet_id') == str(wallet.id) for d in result['discrepancies'])
