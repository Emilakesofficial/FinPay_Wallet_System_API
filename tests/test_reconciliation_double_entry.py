from decimal import Decimal


def _create_user_and_wallets():
    from django.conf import settings
    from django.contrib.auth import get_user_model
    from apps.wallets.models import Wallet
    import uuid

    User = get_user_model()
    suffix = str(uuid.uuid4())[:8]
    user = User.objects.create_user(email=f'bob+{suffix}@example.com', username=f'bob{suffix}', password='pass')

    system_wallet, _ = Wallet.objects.get_or_create(
        is_system=True,
        currency=settings.WALLET_CURRENCY,
        defaults={'name': 'SYSTEM'}
    )
    user_wallet = Wallet.objects.create(user=user, is_system=False, currency=settings.WALLET_CURRENCY, name=f'Bob{suffix}')

    return user, system_wallet, user_wallet


def test_check_double_entry_passes(db):
    """Balanced transaction should pass the double-entry check."""
    from apps.reconciliation import tasks
    from apps.reconciliation.models import ReconciliationReport
    from apps.wallets.models import Transaction, LedgerEntry
    from apps.wallets.constants import EntryType, TransactionType, TransactionStatus

    user, system_wallet, user_wallet = _create_user_and_wallets()

    txn = Transaction.objects.create(
        idempotency_key=f'tx-pass-{user.id}',
        transaction_type=TransactionType.DEPOSIT,
        status=TransactionStatus.COMPLETED,
        amount=Decimal('50.00'),
        currency=user_wallet.currency,
        reference=f'RFPASS-{user.id}',
        initiated_by=user,
    )

    # Create matching debit and credit
    LedgerEntry.objects.create(
        wallet=system_wallet,
        transaction=txn,
        entry_type=EntryType.DEBIT,
        amount=Decimal('50.00'),
        balance_after=Decimal('0.00'),
        description='system debit'
    )

    LedgerEntry.objects.create(
        wallet=user_wallet,
        transaction=txn,
        entry_type=EntryType.CREDIT,
        amount=Decimal('50.00'),
        balance_after=Decimal('50.00'),
        description='user credit'
    )

    report = ReconciliationReport.objects.create()
    res = tasks.check_double_entry.apply(args=(str(report.id),))
    result = res.get(timeout=10)

    assert result['check'] == 'double_entry'
    assert result['passed'] is True
    assert result['issues_count'] == 0


def test_check_double_entry_detects_imbalance(db):
    """Imbalanced transaction (debits != credits) should be reported."""
    from apps.reconciliation import tasks
    from apps.reconciliation.models import ReconciliationReport
    from apps.wallets.models import Transaction, LedgerEntry
    from apps.wallets.constants import EntryType, TransactionType, TransactionStatus

    user, system_wallet, user_wallet = _create_user_and_wallets()

    txn = Transaction.objects.create(
        idempotency_key=f'tx-imb-{user.id}',
        transaction_type=TransactionType.TRANSFER,
        status=TransactionStatus.COMPLETED,
        amount=Decimal('30.00'),
        currency=user_wallet.currency,
        reference=f'RFIMB-{user.id}',
        initiated_by=user,
    )

    # Create debit 30 and credit 20 -> imbalance
    LedgerEntry.objects.create(
        wallet=user_wallet,
        transaction=txn,
        entry_type=EntryType.DEBIT,
        amount=Decimal('30.00'),
        balance_after=Decimal('20.00'),
        description='debit 30'
    )

    LedgerEntry.objects.create(
        wallet=system_wallet,
        transaction=txn,
        entry_type=EntryType.CREDIT,
        amount=Decimal('20.00'),
        balance_after=Decimal('20.00'),
        description='credit 20'
    )

    report = ReconciliationReport.objects.create()
    res = tasks.check_double_entry.apply(args=(str(report.id),))
    result = res.get(timeout=10)

    assert result['check'] == 'double_entry'
    assert result['passed'] is False
    assert result['issues_count'] >= 1
    # At least one discrepancy should reference our transaction
    assert any(d.get('transaction_id') == str(txn.id) for d in result['discrepancies'])
