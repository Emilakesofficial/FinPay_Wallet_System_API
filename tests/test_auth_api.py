"""
Tests for authentication API endpoints.
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
class TestRegistration:
    """Tests for user registration."""
    
    def test_register_success(self, api_client):
        """Test successful user registration."""
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
    
    def test_register_duplicate_email(self, api_client, user):
        """Test registration with duplicate email."""
        url = reverse('accounts:register')
        data = {
            'username': 'different',
            'email': user.email,  # Duplicate
            'password': 'SecurePass123!',
            'password_confirm': 'SecurePass123!',
        }
        
        response = api_client.post(url, data, format='json')
        
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert 'email' in response.data
    
    def test_register_duplicate_username(self, api_client, user):
        """Test registration with duplicate username."""
        url = reverse('accounts:register')
        data = {
            'username': user.username,  # Duplicate
            'email': 'different@example.com',
            'password': 'SecurePass123!',
            'password_confirm': 'SecurePass123!',
        }
        
        response = api_client.post(url, data, format='json')
        
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert 'username' in response.data
    
    def test_register_password_mismatch(self, api_client):
        """Test registration with mismatched passwords."""
        url = reverse('accounts:register')
        data = {
            'username': 'newuser',
            'email': 'newuser@example.com',
            'password': 'SecurePass123!',
            'password_confirm': 'DifferentPass123!',
        }
        
        response = api_client.post(url, data, format='json')
        
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert 'password_confirm' in response.data
    
    def test_register_weak_password(self, api_client):
        """Test registration with weak password."""
        url = reverse('accounts:register')
        data = {
            'username': 'newuser',
            'email': 'newuser@example.com',
            'password': '123',  # Too short
            'password_confirm': '123',
        }
        
        response = api_client.post(url, data, format='json')
        
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert 'password' in response.data


@pytest.mark.django_db
class TestLogin:
    """Tests for user login."""
    
    def test_login_success(self, api_client, user):
        """Test successful login."""
        url = reverse('accounts:login')
        data = {
            'email': user.email,
            'password': 'testpass123'
        }
        
        response = api_client.post(url, data, format='json')
        
        assert response.status_code == status.HTTP_200_OK
        assert 'access' in response.data
        assert 'refresh' in response.data
        assert 'user' in response.data

        # Store tokens for later use
        access_token = response.data['access']
        refresh_token = response.data['refresh']
        assert isinstance(access_token, str)
        assert isinstance(refresh_token, str)
        
        # Verify jwt was created
        assert 'access' in response.data
        assert 'refresh' in response.data

    def test_login_invalid_email(self, api_client):
        """Test login with non-existent email."""
        url = reverse('accounts:login')
        data = {
            'email': 'nonexistent@example.com',
            'password': 'password123'
        }
        
        response = api_client.post(url, data, format='json')
        
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
    
    def test_login_invalid_password(self, api_client, user):
        """Test login with incorrect password."""
        url = reverse('accounts:login')
        data = {
            'email': user.email,
            'password': 'wrongpassword'
        }
        
        response = api_client.post(url, data, format='json')
        
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
    
    def test_login_inactive_user(self, api_client, user):
        """Test login with inactive account."""
        user.is_active = False
        user.save()
        
        url = reverse('accounts:login')
        data = {
            'email': user.email,
            'password': 'testpass123'
        }
        
        response = api_client.post(url, data, format='json')
        
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.django_db
class TestLogout:
    """Tests for user logout."""
    
    def test_logout_success(self, authenticated_client):
        url = reverse('accounts:logout')

        # login to get refresh token
        login_url = reverse('accounts:login')
        login_res = authenticated_client.post(login_url, {
            'email': 'test@example.com',
            'password': 'testpass123'
        }, format='json')

        refresh = login_res.data['refresh']

        response = authenticated_client.post(url, {'refresh': refresh}, format='json')

        assert response.status_code == status.HTTP_200_OK
            
    def test_logout_unauthenticated(self, api_client):
        """Test logout when not authenticated."""
        url = reverse('accounts:logout')
        response = api_client.post(url)
        
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.django_db
class TestProfile:
    """Tests for profile management."""
    
    def test_get_profile(self, authenticated_client, user):
        """Test getting user profile."""
        url = reverse('accounts:profile')
        response = authenticated_client.get(url)
        
        assert response.status_code == status.HTTP_200_OK
        assert response.data['email'] == user.email
        assert response.data['username'] == user.username
    
    def test_update_profile(self, authenticated_client, user):
        """Test updating user profile."""
        url = reverse('accounts:profile')
        original_first_name = user.first_name
        original_last_name = user.last_name
        
        data = {
            'username': 'newusername'
        }
        
        response = authenticated_client.patch(url, data, format='json')
        
        assert response.status_code == status.HTTP_200_OK
        assert response.data['username'] == 'newusername'
        
        # Verify DB update
        user.refresh_from_db()
        assert user.username == 'newusername'

        # Ensure other fields were not modified
        assert user.first_name == original_first_name
        assert user.last_name == original_last_name
        
    def test_update_profile_duplicate_username(self, authenticated_client, user, another_user):
        """Test updating profile with duplicate username."""
        url = reverse('accounts:profile')
        data = {
            'username': another_user.username  # Taken by another user
        }
        
        response = authenticated_client.patch(url, data, format='json')
        
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert 'username' in response.data.get('details', {})

@pytest.mark.django_db
class TestChangePassword:
    """Tests for password change."""
    
    def test_change_password_success(self, authenticated_client, user):
        """Test successful password change."""
        url = reverse('accounts:change-password')
        data = {
            'old_password': 'testpass123',
            'new_password': 'NewSecurePass123!',
            'new_password_confirm': 'NewSecurePass123!'
        }
        
        response = authenticated_client.post(url, data, format='json')
        
        assert response.status_code == status.HTTP_200_OK
        
        # Verify password was changed
        user.refresh_from_db()
        assert user.check_password('NewSecurePass123!')
    
    def test_change_password_wrong_old(self, authenticated_client, user):
        """Test password change with incorrect old password."""
        url = reverse('accounts:change-password')
        data = {
            'old_password': 'wrongpassword',
            'new_password': 'NewSecurePass123!',
            'new_password_confirm': 'NewSecurePass123!'
        }
        
        response = authenticated_client.post(url, data, format='json')
        
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert 'old_password' in response.data
    
    def test_change_password_mismatch(self, authenticated_client, user):
        """Test password change with mismatched new passwords."""
        url = reverse('accounts:change-password')
        data = {
            'old_password': 'testpass123',
            'new_password': 'NewSecurePass123!',
            'new_password_confirm': 'DifferentPass123!'
        }
        
        response = authenticated_client.post(url, data, format='json')
        
        assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
class TestCurrentUser:
    """Tests for current user endpoint."""
    
    def test_get_current_user(self, authenticated_client, user):
        """Test getting current authenticated user."""
        url = reverse('accounts:current-user')
        response = authenticated_client.get(url)
        
        assert response.status_code == status.HTTP_200_OK
        assert str(response.data['id']) == str(user.id)
        assert response.data['email'] == user.email
    
    def test_get_current_user_unauthenticated(self, api_client):
        """Test getting current user when not authenticated."""
        url = reverse('accounts:current-user')
        response = api_client.get(url)
        
        assert response.status_code == status.HTTP_401_UNAUTHORIZED