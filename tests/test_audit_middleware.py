from django.test import RequestFactory
from django.http import HttpResponse


def test_audit_middleware_sets_and_cleans_context(db):
    from apps.audit.middleware import AuditMiddleware, get_request_context
    from django.contrib.auth import get_user_model

    User = get_user_model()
    user = User.objects.create_user(email='mw@example.com', username='mw', password='pass')

    rf = RequestFactory()
    req = rf.get('/')
    req.META['HTTP_USER_AGENT'] = 'unit-test-agent'
    req.META['REMOTE_ADDR'] = '9.9.9.9'
    req.user = user

    captured = {}

    def get_response(request):
        # capture context during request processing
        ctx = get_request_context()
        captured['during'] = ctx
        return HttpResponse('ok')

    mw = AuditMiddleware(get_response)
    resp = mw(req)

    assert resp.status_code == 200
    # During handling, context should be set
    assert captured['during']['ip_address'] == '9.9.9.9'
    assert 'unit-test-agent' in captured['during']['user_agent']

    # After handling, context should be cleaned up (get_request_context returns defaults)
    after = get_request_context()
    assert after['ip_address'] is None
    assert after['user_agent'] == ''
