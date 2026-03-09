def test_auditlog_immutability_and_serializer(db):
    from apps.audit.models import AuditLog
    from apps.audit.serializers import AuditLogSerializer
    from django.contrib.auth import get_user_model

    User = get_user_model()
    user = User.objects.create_user(email='imm@example.com', username='imm', password='pass')

    log = AuditLog.objects.create(
        actor=user,
        action='TEST',
        target_type='Wallet',
        changes={'k': 'v'},
        ip_address='1.1.1.1',
        user_agent='ua',
    )

    # Attempt to update should raise
    try:
        log.action = 'NEW'
        log.save()
        updated = True
    except ValueError:
        updated = False

    assert updated is False

    # Deleting should raise
    try:
        log.delete()
        deleted = True
    except ValueError:
        deleted = False

    assert deleted is False

    # Serializer actor_email
    ser = AuditLogSerializer(log)
    data = ser.data
    assert data['actor_email'] == user.email
