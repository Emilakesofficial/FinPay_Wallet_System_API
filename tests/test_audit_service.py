def test_audit_service_log_and_helpers(db, monkeypatch):
    """AuditService.log should create AuditLog records and helper methods should populate fields."""
    from apps.audit.service import AuditService
    from apps.audit.models import AuditLog, AuditAction
    from apps.wallets.models import Transaction
    from django.contrib.auth import get_user_model
    from apps.audit import middleware
    from decimal import Decimal

    User = get_user_model()
    user = User.objects.create_user(email='auditor@example.com', username='auditor', password='pass')

    # Create a minimal transaction to attach
    txn = Transaction.objects.create(
        idempotency_key='aud-tx-1',
        transaction_type='DEPOSIT',
        status='COMPLETED',
        amount=Decimal('10.00'),
        currency='NGN',
        reference='AUD-REF-1',
        initiated_by=user,
    )

    # Patch get_request_context to include ip and user agent
    monkeypatch.setattr(middleware, 'get_request_context', lambda: {
        'ip_address': '1.2.3.4',
        'user_agent': 'pytest-agent',
        'user': user
    })

    # Call AuditService.log_deposit
    AuditService.log_deposit(txn, actor=user)

    # Verify AuditLog created
    log = AuditLog.objects.filter(action=AuditAction.DEPOSIT).first()
    assert log is not None
    assert log.actor == user
    assert log.target_type == 'Transaction'
    assert 'amount' in log.changes

    # Call other helpers
    AuditService.log_withdrawal(txn, actor=user)
    AuditService.log_transfer(txn, actor=user)

    assert AuditLog.objects.filter(action=AuditAction.WITHDRAWAL).exists()
    assert AuditLog.objects.filter(action=AuditAction.TRANSFER).exists()
