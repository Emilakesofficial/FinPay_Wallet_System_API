"""
Pytest configuration and shared fixtures.
"""
import pytest 
from decimal import Decimal
from django.contrib.auth import get_user_model
from apps.wallets.models import Wallet
from django.conf import settings
from django.urls import reverse

User = get_user_model()

@pytest.fixture
def user(db):
    """Create a test user."""
    return User.objects.create_user(
        username='testuser',
        email='test@example.com',
        password='testpass123'
    )
    
@pytest.fixture(autouse=True)
def use_locmem_cache(settings):
    settings.CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache"
        }
    }

@pytest.fixture
def another_user(db):
    """Create another test user."""
    return User.objects.create_user(
        username='anotheruser',
        email='another@example.com',
        password='testpass123'
    )
# 🔹 JWT Authenticated client
@pytest.fixture
def authenticated_client(api_client, user):
    login_url = reverse('accounts:login')
    response = api_client.post(login_url, {
        'email': user.email,
        'password': 'testpass123'
    }, format='json')

    token = response.data['access']
    api_client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')
    return api_client

# 🔹 Disable throttling globally in tests
@pytest.fixture(autouse=True)
def disable_throttling(settings):
    settings.REST_FRAMEWORK = {
        **settings.REST_FRAMEWORK,
        'DEFAULT_THROTTLE_CLASSES': [],
        'DEFAULT_THROTTLE_RATES': {
            'anon': '10000/min',
            'user': '10000/min',
            'transactions': '100/hour',
            'auth': '10000/min',   # ← prevents crash
            'burst': '10000/min',
            'sustained': '10000/day',
        }
    }
    
@pytest.fixture
def wallet(db, user):
    """Create a test wallet."""
    existing_wallet = Wallet.objects.filter(user=user).first()
    if existing_wallet:
        return existing_wallet
    
    return Wallet.objects.create(
        user=user,
        currency='NGN',
        name='Test Wallet',
    )
    
@pytest.fixture
def another_wallet(another_user):
    """Create another test wallet."""
    # Check if user already has a wallet (from signal or registration)
    existing_wallet = Wallet.objects.filter(user=another_user).first()
    if existing_wallet:
        return existing_wallet
    
    return Wallet.objects.create(
        user=another_user,
        currency='NGN',
        name='Another User Test Wallet',
    )
    
@pytest.fixture(autouse=True, scope='function')
def system_wallet(django_db_blocker):
    """Create or get system wallet for all tests."""
    with django_db_blocker.unblock():
        wallet, _ = Wallet.objects.get_or_create(
            is_system=True,
            currency='NGN',
            defaults={'name': 'SYSTEM'}
        )
    return wallet