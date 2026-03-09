"""
Tests for wallet API endpoints.
"""
import pytest
import uuid
from decimal import Decimal
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient
from apps.wallets.models import Wallet, Transaction
from apps.wallets.services import WalletService

def get_balance_from_response(response_data):
    """
    Extract balance from response data, handling both Decimal and string formats.
    """
    balance = response_data.get('balance')
    if balance is None:
        return Decimal('0.00')
    return Decimal(str(balance))

@pytest.fixture
def api_client():
    """Create API client."""
    return APIClient()


@pytest.fixture
def authenticated_client(api_client, user):
    """Create authenticated API client."""
    api_client.force_authenticate(user=user)
    return api_client


def normalize_decimal(value):
    """Normalize value to Decimal for comparison."""
    if isinstance(value, str):
        return Decimal(value)
    return Decimal(str(value))


@pytest.mark.django_db
class TestWalletAPI:
    """Tests for wallet API endpoints."""
    
    def test_create_wallet(self, authenticated_client, user):
        """Test creating a wallet via API."""
        url = reverse('wallets:wallet-list')
        data = {
            'currency': 'NGN',
            'name': 'My Test Wallet'
        }
        
        response = authenticated_client.post(url, data, format='json')
        
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data['currency'] == 'NGN'
        assert response.data['name'] == 'My Test Wallet'
        # Compare as Decimal
        assert normalize_decimal(response.data['balance']) == Decimal('0.00')
        
        # Verify wallet was created
        assert Wallet.objects.filter(user=user, currency='NGN').exists()
    
    def test_list_wallets(self, authenticated_client, wallet):
        """Test listing wallets."""
        url = reverse('wallets:wallet-list')
        response = authenticated_client.get(url)
        
        assert response.status_code == status.HTTP_200_OK
        # Handle paginated or non-paginated response
        data = response.data.get('results', response.data)
        if isinstance(data, list):
            wallet_ids = [w['id'] for w in data]
            assert str(wallet.id) in wallet_ids
        else:
            assert len(response.data) >= 1
    
    def test_get_wallet_detail(self, authenticated_client, wallet):
        """Test getting wallet details."""
        url = reverse('wallets:wallet-detail', kwargs={'pk': wallet.id})
        response = authenticated_client.get(url)
        
        assert response.status_code == status.HTTP_200_OK
        assert response.data['id'] == str(wallet.id)
        assert response.data['currency'] == wallet.currency
    
    def test_cannot_access_other_user_wallet(self, authenticated_client, another_wallet):
        """Test that users can't access other users' wallets."""
        url = reverse('wallets:wallet-detail', kwargs={'pk': another_wallet.id})
        response = authenticated_client.get(url)
        
        assert response.status_code == status.HTTP_404_NOT_FOUND
    
    def test_get_wallet_balance(self, authenticated_client, wallet, user):
        """Test getting wallet balance."""
        # Setup: deposit some money
        WalletService.deposit(
            wallet_id=str(wallet.id),
            amount=Decimal('123.45'),
            idempotency_key=f'api-balance-test-{uuid.uuid4()}',
            initiated_by=user
        )
        
        url = reverse('wallets:wallet-balance', kwargs={'pk': wallet.id})
        response = authenticated_client.get(url)
        
        assert response.status_code == status.HTTP_200_OK
        assert normalize_decimal(response.data['balance']) == Decimal('123.45')
    
    def test_get_wallet_statement(self, authenticated_client, wallet, user):
        """Test getting wallet statement."""
        # Setup: perform some transactions
        WalletService.deposit(
            wallet_id=str(wallet.id),
            amount=Decimal('100.00'),
            idempotency_key=f'stmt-test-1-{uuid.uuid4()}',
            initiated_by=user
        )
        
        WalletService.withdraw(
            wallet_id=str(wallet.id),
            amount=Decimal('30.00'),
            idempotency_key=f'stmt-test-2-{uuid.uuid4()}',
            initiated_by=user
        )
        
        url = reverse('wallets:wallet-statement', kwargs={'pk': wallet.id})
        response = authenticated_client.get(url)
        
        assert response.status_code == status.HTTP_200_OK
        # Handle paginated or non-paginated response
        data = response.data
        assert isinstance(data, list)
        assert len(data) >= 2  # At least 2 ledger entries

@pytest.mark.django_db
class TestDepositAPI:
    """Tests for deposit API endpoint."""
    
    def test_deposit_success(self, authenticated_client, wallet):
        """Test successful deposit via API."""
        url = reverse('wallets:transaction-deposit')
        data = {
            'wallet_id': str(wallet.id),
            'amount': '250.00',
            'description': 'API test deposit'
        }
        headers = {'HTTP_IDEMPOTENCY_KEY': f'api-deposit-{uuid.uuid4()}'}
        
        response = authenticated_client.post(url, data, format='json', **headers)
        
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data['transaction_type'].upper() == 'DEPOSIT'
        assert normalize_decimal(response.data['amount']) == Decimal('250.00')
        assert response.data['status'].upper() == 'COMPLETED'
        
        # Verify balance
        wallet.refresh_from_db()
        assert wallet.get_balance() == Decimal('250.00')
    
    def test_deposit_without_idempotency_key(self, authenticated_client, wallet):
        """Test that deposit requires idempotency key."""
        url = reverse('wallets:transaction-deposit')
        data = {
            'wallet_id': str(wallet.id),
            'amount': '100.00'
        }
        
        response = authenticated_client.post(url, data, format='json')
        
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert 'idempotency' in str(response.data).lower()
    
    def test_deposit_idempotency(self, authenticated_client, wallet):
        """Test deposit idempotency via API."""
        url = reverse('wallets:transaction-deposit')
        idempotency_key = f'api-deposit-idemp-{uuid.uuid4()}'
        data = {
            'wallet_id': str(wallet.id),
            'amount': '100.00'
        }
        headers = {'HTTP_IDEMPOTENCY_KEY': idempotency_key}
        
        # First request
        response1 = authenticated_client.post(url, data, format='json', **headers)
        assert response1.status_code == status.HTTP_201_CREATED
        txn_id_1 = response1.data['id']
        
        # Second request with same idempotency key but different amount
        data['amount'] = '200.00'
        response2 = authenticated_client.post(url, data, format='json', **headers)
        assert response2.status_code == status.HTTP_201_CREATED
        txn_id_2 = response2.data['id']
        
        # Should return same transaction
        assert txn_id_1 == txn_id_2
        assert normalize_decimal(response2.data['amount']) == Decimal('100.00')  # Original amount
        
        # Balance should reflect only one deposit
        wallet.refresh_from_db()
        assert wallet.get_balance() == Decimal('100.00')
    
    def test_deposit_invalid_amount(self, authenticated_client, wallet):
        """Test deposit with invalid amount."""
        url = reverse('wallets:transaction-deposit')
        data = {
            'wallet_id': str(wallet.id),
            'amount': '-50.00'  # Negative amount
        }
        headers = {'HTTP_IDEMPOTENCY_KEY': f'api-deposit-invalid-{uuid.uuid4()}'}
        
        response = authenticated_client.post(url, data, format='json', **headers)
        
        assert response.status_code == status.HTTP_400_BAD_REQUEST
    
    def test_deposit_to_other_user_wallet(self, authenticated_client, another_wallet):
        """Test that user cannot deposit to another user's wallet."""
        url = reverse('wallets:transaction-deposit')
        data = {
            'wallet_id': str(another_wallet.id),
            'amount': '100.00'
        }
        headers = {'HTTP_IDEMPOTENCY_KEY': f'api-deposit-other-{uuid.uuid4()}'}
        
        response = authenticated_client.post(url, data, format='json', **headers)
        
        assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db
class TestWithdrawAPI:
    """Tests for withdrawal API endpoint."""
    
    def test_withdraw_success(self, authenticated_client, wallet, user):
        """Test successful withdrawal via API."""
        # Setup: deposit money first
        WalletService.deposit(
            wallet_id=str(wallet.id),
            amount=Decimal('500.00'),
            idempotency_key=f'withdraw-api-setup-{uuid.uuid4()}',
            initiated_by=user
        )
        
        url = reverse('wallets:transaction-withdraw')
        data = {
            'wallet_id': str(wallet.id),
            'amount': '150.00',
            'description': 'API test withdrawal'
        }
        headers = {'HTTP_IDEMPOTENCY_KEY': f'api-withdraw-{uuid.uuid4()}'}
        
        response = authenticated_client.post(url, data, format='json', **headers)
        
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data['transaction_type'].upper() == 'WITHDRAWAL'
        assert normalize_decimal(response.data['amount']) == Decimal('150.00')
        assert response.data['status'].upper() == 'COMPLETED'
        
        # Verify balance
        wallet.refresh_from_db()
        assert wallet.get_balance() == Decimal('350.00')
    
    def test_withdraw_insufficient_funds(self, authenticated_client, wallet, user):
        """Test withdrawal with insufficient funds."""
        # Deposit only $50
        WalletService.deposit(
            wallet_id=str(wallet.id),
            amount=Decimal('50.00'),
            idempotency_key=f'withdraw-insufficient-setup-{uuid.uuid4()}',
            initiated_by=user
        )
        
        url = reverse('wallets:transaction-withdraw')
        data = {
            'wallet_id': str(wallet.id),
            'amount': '100.00'  # Try to withdraw more than balance
        }
        headers = {'HTTP_IDEMPOTENCY_KEY': f'api-withdraw-insufficient-{uuid.uuid4()}'}
        
        response = authenticated_client.post(url, data, format='json', **headers)
        
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert 'insufficient' in str(response.data).lower()


@pytest.mark.django_db
class TestTransferAPI:
    """Tests for transfer API endpoint."""
    
    def test_transfer_success(self, authenticated_client, wallet, another_wallet, user):
        """Test successful transfer via API."""
        # Setup: deposit to sender
        WalletService.deposit(
            wallet_id=str(wallet.id),
            amount=Decimal('1000.00'),
            idempotency_key=f'transfer-api-setup-{uuid.uuid4()}',
            initiated_by=user
        )
        
        url = reverse('wallets:transaction-transfer')
        data = {
            'from_wallet_id': str(wallet.id),
            'to_wallet_id': str(another_wallet.id),
            'amount': '300.00',
            'description': 'API test transfer'
        }
        headers = {'HTTP_IDEMPOTENCY_KEY': f'api-transfer-{uuid.uuid4()}'}
        
        response = authenticated_client.post(url, data, format='json', **headers)
        
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data['transaction_type'].upper() == 'TRANSFER'
        assert normalize_decimal(response.data['amount']) == Decimal('300.00')
        assert response.data['status'].upper() == 'COMPLETED'
        
        # Verify balances
        wallet.refresh_from_db()
        another_wallet.refresh_from_db()
        
        assert wallet.get_balance() == Decimal('700.00')
        assert another_wallet.get_balance() == Decimal('300.00')
    
    def test_transfer_to_same_wallet(self, authenticated_client, wallet, user):
        """Test that transfer to same wallet is rejected."""
        WalletService.deposit(
            wallet_id=str(wallet.id),
            amount=Decimal('500.00'),
            idempotency_key=f'transfer-same-setup-{uuid.uuid4()}',
            initiated_by=user
        )
        
        url = reverse('wallets:transaction-transfer')
        data = {
            'from_wallet_id': str(wallet.id),
            'to_wallet_id': str(wallet.id),
            'amount': '100.00'
        }
        headers = {'HTTP_IDEMPOTENCY_KEY': f'api-transfer-same-{uuid.uuid4()}'}
        
        response = authenticated_client.post(url, data, format='json', **headers)
        
        assert response.status_code == status.HTTP_400_BAD_REQUEST
    
    def test_transfer_from_other_user_wallet(self, authenticated_client, another_wallet, wallet):
        """Test that user cannot transfer from another user's wallet."""
        url = reverse('wallets:transaction-transfer')
        data = {
            'from_wallet_id': str(another_wallet.id),
            'to_wallet_id': str(wallet.id),
            'amount': '100.00'
        }
        headers = {'HTTP_IDEMPOTENCY_KEY': f'api-transfer-unauthorized-{uuid.uuid4()}'}
        
        response = authenticated_client.post(url, data, format='json', **headers)
        
        assert response.status_code == status.HTTP_404_NOT_FOUND
    
    def test_transfer_insufficient_funds(self, authenticated_client, wallet, another_wallet, user):
        """Test transfer with insufficient funds."""
        # Deposit only $50
        WalletService.deposit(
            wallet_id=str(wallet.id),
            amount=Decimal('50.00'),
            idempotency_key=f'transfer-insufficient-setup-{uuid.uuid4()}',
            initiated_by=user
        )
        
        url = reverse('wallets:transaction-transfer')
        data = {
            'from_wallet_id': str(wallet.id),
            'to_wallet_id': str(another_wallet.id),
            'amount': '100.00'
        }
        headers = {'HTTP_IDEMPOTENCY_KEY': f'api-transfer-insufficient-{uuid.uuid4()}'}
        
        response = authenticated_client.post(url, data, format='json', **headers)
        
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert 'insufficient' in str(response.data).lower()


@pytest.mark.django_db
class TestTransactionAPI:
    """Tests for transaction API endpoints."""
    
    def test_list_transactions(self, authenticated_client, wallet, user):
        """Test listing transactions."""
        # Setup: create some transactions
        WalletService.deposit(
            wallet_id=str(wallet.id),
            amount=Decimal('100.00'),
            idempotency_key=f'txn-list-1-{uuid.uuid4()}',
            initiated_by=user
        )
        
        WalletService.withdraw(
            wallet_id=str(wallet.id),
            amount=Decimal('30.00'),
            idempotency_key=f'txn-list-2-{uuid.uuid4()}',
            initiated_by=user
        )
        
        url = reverse('wallets:transaction-list')
        response = authenticated_client.get(url)
        
        assert response.status_code == status.HTTP_200_OK
        # Handle paginated or non-paginated response
        response_data = response.data
        if isinstance(response_data, list):
            data = response_data
        else:
            data = response_data.get('results', response_data)
        # We created 2 new transactions
        assert len(data) >= 2
    
    def test_get_transaction_detail(self, authenticated_client, wallet, user):
        """Test getting transaction details."""
        # Create a transaction
        txn = WalletService.deposit(
            wallet_id=str(wallet.id),
            amount=Decimal('100.00'),
            idempotency_key=f'txn-detail-{uuid.uuid4()}',
            initiated_by=user
        )
        
        url = reverse('wallets:transaction-detail', kwargs={'pk': txn.id})
        response = authenticated_client.get(url)
        
        assert response.status_code == status.HTTP_200_OK
        assert response.data['id'] == str(txn.id)
        assert normalize_decimal(response.data['amount']) == Decimal('100.00')
        # Check for ledger entries if they exist in response
        if 'ledger_entries' in response.data:
            assert len(response.data['ledger_entries']) >= 2  # Double-entry
    
    def test_cannot_access_other_user_transaction(
        self, authenticated_client, another_wallet, another_user
    ):
        """Test that user cannot access another user's transactions."""
        # Create transaction for another user
        txn = WalletService.deposit(
            wallet_id=str(another_wallet.id),
            amount=Decimal('100.00'),
            idempotency_key=f'txn-other-user-{uuid.uuid4()}',
            initiated_by=another_user
        )
        
        url = reverse('wallets:transaction-detail', kwargs={'pk': txn.id})
        response = authenticated_client.get(url)
        
        assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db
class TestAuthenticationRequired:
    """Tests for authentication requirements."""
    
    def test_unauthenticated_wallet_list(self, api_client):
        """Test that unauthenticated wallet list is rejected."""
        url = reverse('wallets:wallet-list')
        response = api_client.get(url)
        
        assert response.status_code in [
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN
        ]
    
    def test_unauthenticated_transaction_list(self, api_client):
        """Test that unauthenticated transaction list is rejected."""
        url = reverse('wallets:transaction-list')
        response = api_client.get(url)
        
        assert response.status_code in [
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN
        ]
    
    def test_unauthenticated_deposit(self, api_client, wallet):
        """Test that unauthenticated deposit is rejected."""
        url = reverse('wallets:transaction-deposit')
        data = {
            'wallet_id': str(wallet.id),
            'amount': '100.00'
        }
        headers = {'HTTP_IDEMPOTENCY_KEY': f'auth-test-{uuid.uuid4()}'}
        
        response = api_client.post(url, data, format='json', **headers)
        
        assert response.status_code in [
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN
        ]
    
    def test_unauthenticated_withdraw(self, api_client, wallet):
        """Test that unauthenticated withdrawal is rejected."""
        url = reverse('wallets:transaction-withdraw')
        data = {
            'wallet_id': str(wallet.id),
            'amount': '100.00'
        }
        headers = {'HTTP_IDEMPOTENCY_KEY': f'auth-test-{uuid.uuid4()}'}
        
        response = api_client.post(url, data, format='json', **headers)
        
        assert response.status_code in [
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN
        ]
    
    def test_unauthenticated_transfer(self, api_client, wallet, another_wallet):
        """Test that unauthenticated transfer is rejected."""
        url = reverse('wallets:transaction-transfer')
        data = {
            'from_wallet_id': str(wallet.id),
            'to_wallet_id': str(another_wallet.id),
            'amount': '100.00'
        }
        headers = {'HTTP_IDEMPOTENCY_KEY': f'auth-test-{uuid.uuid4()}'}
        
        response = api_client.post(url, data, format='json', **headers)
        
        assert response.status_code in [
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN
        ]