"""
Pytest configuration and shared fixtures.
"""
import pytest 
from decimal import Decimal
from django.contrib.auth import get_user_model
from apps.wallets.models import Wallet
from apps.wallets.constants import TransactionType

User = get_user_model()

@pytest.fixture
def user(db):
    """Create a test user."""
    return User.objects.create_user(
        username='testuser',
        email='test@example.com',
        password='testpass123'
    )

@pytest.fixture
def another_user(db):
    """Create another test user."""
    return User.objects.create_user(
        username='anotheruser',
        email='another@example.com',
        password='testpass123'
    )
    
@pytest.fixture
def wallet(db, user):
    """Create a test wallet."""
    return Wallet.objects.create(
        user=user,
        currency='NGN',
        name='Test Wallet'
    )
    
@pytest.fixture
def another_wallet(db, another_user):
    """Create another test wallet."""
    return Wallet.objects.create(
        user=another_user,
        currency='NGN',
        name='Another Test Wallet'
    )
    
@pytest.fixture
def system_wallet(db):
    """Create a system wallet."""
    return Wallet.objects.create(
        is_system=True,
        currency='NGN',
        name='SYSTEM'
    )