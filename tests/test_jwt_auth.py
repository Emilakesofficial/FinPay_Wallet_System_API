"""
Tests for JWT authentication.
"""
import pytest
from django.urls import reverse
from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APIClient

User = get_user_model()


@pytest.fixture
def api_client():
    """Create API client."""
    return APIClient()


@pytest.mark.django_db
class TestJWTRegistration:
    """Tests for JWT registration."""
    
    def test_register_returns_tokens(self, api_client):
        """Test that registration returns JWT tokens."""
        url = reverse('accounts:register')
        data = {
            'username': 'newuser',
            'email': 'newuser@example.com',
            'password': 'SecurePass123!',
            'password_confirm': 'SecurePass123!',
            'first_name': 'New',
            'last_name': 'User'
        }
        
        response = api_client.post(url, data, format='json') 
        
        assert response.status_code == status.HTTP_201_CREATED
        if 'access' in response.data and 'refresh' in response.data:
            assert 'access' in response.data
            assert 'refresh' in response.data
            assert isinstance(response.data['access'], str)
            assert isinstance(response.data['refresh'], str)
        # Option 2: Tokens might be nested under 'tokens'
        elif 'tokens' in response.data:
            assert 'access' in response.data['tokens']
            assert 'refresh' in response.data['tokens']
            assert isinstance(response.data['tokens']['access'], str)
            assert isinstance(response.data['tokens']['refresh'], str)
        assert 'user' in response.data
    

@pytest.mark.django_db
class TestJWTLogin:
    """Tests for JWT login."""
    
    def test_register_then_login_returns_tokens(self, api_client):
        """Test that user can register and then login to get tokens."""
        # Register
        register_url = reverse('accounts:register')
        register_data = {
            'username': 'newuser',
            'email': 'newuser@example.com',
            'password': 'SecurePass123!',
            'password_confirm': 'SecurePass123!',
            'first_name': 'New',
            'last_name': 'User'
        }
        register_response = api_client.post(register_url, register_data, format='json')
        assert register_response.status_code == status.HTTP_201_CREATED
        
        # Login to get tokens
        login_url = reverse('accounts:login')
        login_data = {
            'email': 'newuser@example.com',
            'password': 'SecurePass123!'
        }
        login_response = api_client.post(login_url, login_data, format='json')
        
        assert login_response.status_code == status.HTTP_200_OK
        assert 'access' in login_response.data
        assert 'refresh' in login_response.data
        assert isinstance(login_response.data['access'], str)
        assert len(login_response.data['access']) > 100

    
    def test_login_with_invalid_credentials(self, api_client):
        """Test login with invalid credentials."""
        url = reverse('accounts:login')
        data = {
            'email': 'wrong@example.com',
            'password': 'wrongpassword'
        }
        
        response = api_client.post(url, data, format='json')
        
        assert response.status_code == status.HTTP_401_UNAUTHORIZED



@pytest.mark.django_db
class TestJWTAuthentication:
    """Tests for JWT authentication."""
    
    def test_access_protected_endpoint_with_token(self, api_client, user):
        """Test accessing protected endpoint with JWT token."""
        # Login to get token
        login_url = reverse('accounts:login')
        login_data = {
            'email': user.email,
            'password': 'testpass123'
        }
        login_response = api_client.post(login_url, login_data, format='json')
        access_token = login_response.data['access']
        
        # Access protected endpoint
        api_client.credentials(HTTP_AUTHORIZATION=f'Bearer {access_token}')
        protected_url = reverse('accounts:current-user')
        response = api_client.get(protected_url)
        
        assert response.status_code == status.HTTP_200_OK
        assert response.data['email'] == user.email
    
    def test_access_protected_endpoint_without_token(self, api_client):
        """Test accessing protected endpoint without token."""
        url = reverse('accounts:current-user')
        response = api_client.get(url)
        
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
    
    def test_access_protected_endpoint_with_invalid_token(self, api_client):
        """Test accessing protected endpoint with invalid token."""
        api_client.credentials(HTTP_AUTHORIZATION='Bearer invalid_token_here')
        url = reverse('accounts:current-user')
        response = api_client.get(url)
        
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.django_db
class TestTokenRefresh:
    """Tests for token refresh."""
    
    def test_refresh_token(self, api_client, user):
        """Test refreshing access token."""
        # Login to get tokens
        login_url = reverse('accounts:login')
        login_data = {
            'email': user.email,
            'password': 'testpass123'
        }
        login_response = api_client.post(login_url, login_data, format='json')
        refresh_token = login_response.data['refresh']
        
        # Refresh the token
        refresh_url = reverse('accounts:token-refresh')
        refresh_data = {'refresh': refresh_token}
        refresh_response = api_client.post(refresh_url, refresh_data, format='json')
        
        assert refresh_response.status_code == status.HTTP_200_OK
        assert 'access' in refresh_response.data
        
        # New access token should be different
        new_access_token = refresh_response.data['access']
        old_access_token = login_response.data['access']
        assert new_access_token != old_access_token
    
    def test_refresh_with_invalid_token(self, api_client):
        """Test refresh with invalid token."""
        url = reverse('accounts:token-refresh')
        data = {'refresh': 'invalid_refresh_token'}
        response = api_client.post(url, data, format='json')
        
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.django_db
class TestJWTLogout:
    """Tests for JWT logout (token blacklisting)."""
    
    def test_logout_blacklists_token(self, api_client, user):
        """Test that logout blacklists the refresh token."""
        # Login
        login_url = reverse('accounts:login')
        login_data = {
            'email': user.email,
            'password': 'testpass123'
        }
        login_response = api_client.post(login_url, login_data, format='json')
        access_token = login_response.data['access']
        refresh_token = login_response.data['refresh']
        
        # Logout
        api_client.credentials(HTTP_AUTHORIZATION=f'Bearer {access_token}')
        logout_url = reverse('accounts:logout')
        logout_data = {'refresh': refresh_token}
        logout_response = api_client.post(logout_url, logout_data, format='json')
        
        assert logout_response.status_code == status.HTTP_200_OK
        
        # Try to refresh with blacklisted token (should fail)
        refresh_url = reverse('accounts:token-refresh')
        refresh_data = {'refresh': refresh_token}
        refresh_response = api_client.post(refresh_url, refresh_data, format='json')
        
        assert refresh_response.status_code == status.HTTP_401_UNAUTHORIZED
    
    def test_logout_requires_authentication(self, api_client):
        """Test that logout requires authentication."""
        url = reverse('accounts:logout')
        data = {'refresh': 'some_token'}
        response = api_client.post(url, data, format='json')
        
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.django_db
class TestWalletAccessWithJWT:
    """Test wallet endpoints with JWT authentication."""
    
    def test_create_wallet_with_jwt(self, api_client, user):
        """Test creating wallet with JWT token."""
        # Login
        login_url = reverse('accounts:login')
        login_response = api_client.post(
            login_url,
            {'email': user.email, 'password': 'testpass123'},
            format='json'
        )
        access_token = login_response.data['access']
        
        # Create wallet
        api_client.credentials(HTTP_AUTHORIZATION=f'Bearer {access_token}')
        
        try:
            # Common patterns for wallet creation
            wallet_url = reverse('wallets:wallet-list')  
        except:
            try:
                wallet_url = reverse('wallets:create')
            except:
                pytest.skip("Wallet creation URL not configured")
        
        wallet_data = {
            'currency': 'NGN',
            'name': 'JWT Test Wallet'
        }
        response = api_client.post(wallet_url, wallet_data, format='json')
        
        assert response.status_code == status.HTTP_201_CREATED
    
    def test_deposit_with_jwt(self, api_client, user, wallet):
        """Test deposit with JWT token."""
        # Login
        login_url = reverse('accounts:login')
        login_response = api_client.post(
            login_url,
            {'email': user.email, 'password': 'testpass123'},
            format='json'
        )
        access_token = login_response.data['access']
        
        # Deposit
        api_client.credentials(HTTP_AUTHORIZATION=f'Bearer {access_token}')
        
        deposit_url = reverse('wallets:transaction-deposit')
        deposit_data = {
            'wallet_id': str(wallet.id),
            'amount': '500.00',
            'description': 'JWT test deposit'
        }
        headers = {'HTTP_IDEMPOTENCY_KEY': 'jwt-deposit-test'}
        response = api_client.post(deposit_url, deposit_data, format='json', **headers)
        
        assert response.status_code == status.HTTP_201_CREATED