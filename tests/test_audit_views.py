from rest_framework.test import APIClient


def test_audit_views_list_summary_and_actions(db):
    from apps.audit.models import AuditLog, AuditAction
    from django.contrib.auth import get_user_model
    from django.urls import reverse
    from django.utils import timezone

    User = get_user_model()
    admin = User.objects.create_user(email='admin@example.com', username='admin', password='pass', is_staff=True)

    # Create some audit logs
    for i in range(3):
        AuditLog.objects.create(
            actor=admin,
            action=AuditAction.USER_LOGIN,
            target_type='User',
            changes={'i': i},
            ip_address='1.2.3.4',
            user_agent='ua',
        )

    client = APIClient()
    client.force_authenticate(user=admin)

    # List
    resp = client.get('/api/v1/audit/')
    assert resp.status_code == 200
    assert len(resp.data) >= 3

    # Summary
    resp = client.get('/api/v1/audit/summary/')
    assert resp.status_code == 200
    assert 'total_logs' in resp.data

    # Actions
    resp = client.get('/api/v1/audit/actions/')
    assert resp.status_code == 200
    assert 'actions' in resp.data
