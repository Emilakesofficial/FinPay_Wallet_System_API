"""
API views for wallet operations.
Clean production-grade architecture with ModelViewSet.
"""
import logging
from rest_framework import status, viewsets, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema, OpenApiParameter

from .models import Wallet, Transaction
from .services import WalletService
from .selectors import WalletSelectors
from .serializers import (
    WalletSerializer,
    TransactionSerializer,
    LedgerEntrySerializer,
    DepositSerializer,
    WithdrawSerializer,
    TransferSerializer,
    BalanceSerializer,
)
from common.throttling import TransactionRateThrottle
from common.exceptions import (
    WalletNotFoundException, TransactionFailedException
)

logger = logging.getLogger(__name__)


class WalletViewSet(viewsets.ModelViewSet):
    """
    ViewSet for wallet CRUD operations.
    
    Endpoints:
    - GET /wallets/ - List user's wallets
    - POST /wallets/ - Create new wallet
    - GET /wallets/{id}/ - Get wallet detail
    - GET /wallets/{id}/balance/ - Get wallet balance
    - GET /wallets/{id}/statement/ - Get wallet statement
    """
    serializer_class = WalletSerializer
    permission_classes = [permissions.IsAuthenticated]
    http_method_names = ['get', 'post']  # Read + Create only
    
    def get_queryset(self):
        """Return wallets for the authenticated user."""
        return Wallet.objects.filter(
            user=self.request.user
        ).order_by('-created_at')
    
    def perform_create(self, serializer):
        """Create wallet for the authenticated user."""
        serializer.save(user=self.request.user)
    
    @action(detail=True, methods=['get'])
    def balance(self, request, pk=None):
        wallet = self.get_object()

        try:
            balance_info = WalletService.get_balance(str(wallet.id))
            serializer = BalanceSerializer(balance_info)
            return Response(serializer.data)

        except WalletException as e:
            return Response({'error': str(e)}, status=e.status_code)

        except Exception as e:
            # Log the real error
            import traceback
            traceback.print_exc()

            return Response(
                {'error': 'Internal server error'},
                status=500
            )
    
    @action(detail=True, methods=['get'])
    def statement(self, request, pk=None):
        """Get wallet statement (ledger entries)."""
        wallet = self.get_object()
        
        entries = WalletSelectors.get_wallet_statement(
            wallet_id=str(wallet.id),
            limit=100
        )
        
        serializer = LedgerEntrySerializer(entries, many=True)
        return Response(serializer.data)

@extend_schema(tags=['Transactions'])
class TransactionViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for transaction operations with rate limiting.
    Endpoints:
    - GET /transactions/ - List user's transactions
    - GET /transactions/{id}/ - Get transaction detail
    - POST /transactions/deposit/ - Deposit money
    - POST /transactions/withdraw/ - Withdraw money
    - POST /transactions/transfer/ - Transfer money
    """
    serializer_class = TransactionSerializer
    permission_classes = [permissions.IsAuthenticated]
    throttle_classes = [TransactionRateThrottle]
    
    def get_queryset(self):
        """Return transactions for user's wallets."""
        user_wallet_ids = Wallet.objects.filter(
            user=self.request.user
        ).values_list('id', flat=True)
        
        return Transaction.objects.filter(
            ledger_entries__wallet_id__in=user_wallet_ids
        ).distinct().order_by('-created_at')
    
    @extend_schema(
        request=DepositSerializer,
        responses={201: TransactionSerializer},
        parameters=[
            OpenApiParameter(
                name='Idempotency-Key',
                type=str,
                location=OpenApiParameter.HEADER,
                required=True,
                description='Unique key to prevent duplicate transactions'
            ),
        ],
    )
    @action(detail=False, methods=['post'])
    def deposit(self, request):
        """Deposit money into a wallet - rate limited to 30/hour per user."""
        # Validate idempotency key
        idempotency_key = request.META.get('HTTP_IDEMPOTENCY_KEY')
        if not idempotency_key:
            return Response(
                {'error': 'Idempotency-Key header is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Validate request
        serializer = DepositSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        
        # Verify wallet ownership
        wallet = get_object_or_404(
            Wallet,
            id=data['wallet_id'],
            user=request.user
        )
        
        try:
            # Execute deposit
            transaction = WalletService.deposit(
                wallet_id=str(data['wallet_id']),
                amount=data['amount'],
                idempotency_key=idempotency_key,
                initiated_by=request.user,
                description=data.get('description', ''),
                metadata=data.get('metadata', {})
            )
            
            serializer = TransactionSerializer(transaction)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
            
        except TransactionFailedException as e:
            logger.error(f"Deposit failed: {e}")
            return Response(
                {
                    'error': e.__class__.__name__,
                    'message': e.message,
                    'details': e.extra
                },
                status=e.status_code
            )
    
    @extend_schema(
        request=WithdrawSerializer,
        responses={201: TransactionSerializer},
        parameters=[
            OpenApiParameter(
                name='Idempotency-Key',
                type=str,
                location=OpenApiParameter.HEADER,
                required=True,
                description='Unique key to prevent duplicate transactions'
            ),
        ],
    )
    @action(detail=False, methods=['post'])
    def withdraw(self, request):
        """Withdraw money from a wallet - rate limited to 30/hour per user."""
        # Validate idempotency key
        idempotency_key = request.META.get('HTTP_IDEMPOTENCY_KEY')
        if not idempotency_key:
            return Response(
                {'error': 'Idempotency-Key header is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Validate request
        serializer = WithdrawSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        
        # Verify wallet ownership
        wallet = get_object_or_404(
            Wallet,
            id=data['wallet_id'],
            user=request.user
        )
        
        try:
            # Execute withdrawal
            transaction = WalletService.withdraw(
                wallet_id=str(data['wallet_id']),
                amount=data['amount'],
                idempotency_key=idempotency_key,
                initiated_by=request.user,
                description=data.get('description', ''),
                metadata=data.get('metadata', {})
            )
            
            serializer = TransactionSerializer(transaction)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
            
        except TransactionFailedException as e:
            logger.error(f"Withdrawal failed: {e}")
            return Response(
                {
                    'error': e.__class__.__name__,
                    'message': e.message,
                    'details': e.extra
                },
                status=e.status_code
            )
    
    @extend_schema(
        request=TransferSerializer,
        responses={201: TransactionSerializer},
        parameters=[
            OpenApiParameter(
                name='Idempotency-Key',
                type=str,
                location=OpenApiParameter.HEADER,
                required=True,
                description='Unique key to prevent duplicate transactions'
            ),
        ],
    )
    @action(detail=False, methods=['post'])
    def transfer(self, request):
        """Transfer money between wallets - rate limited to 50/hour per user."""
        # Validate idempotency key
        idempotency_key = request.META.get('HTTP_IDEMPOTENCY_KEY')
        if not idempotency_key:
            return Response(
                {'error': 'Idempotency-Key header is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Validate request
        serializer = TransferSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        
        # Verify source wallet ownership
        from_wallet = get_object_or_404(
            Wallet,
            id=data['from_wallet_id'],
            user=request.user
        )
        
        # Verify destination wallet exists
        to_wallet = get_object_or_404(
            Wallet,
            id=data['to_wallet_id']
        )
        
        try:
            # Execute transfer
            transaction = WalletService.transfer(
                from_wallet_id=str(data['from_wallet_id']),
                to_wallet_id=str(data['to_wallet_id']),
                amount=data['amount'],
                idempotency_key=idempotency_key,
                initiated_by=request.user,
                description=data.get('description', ''),
                metadata=data.get('metadata', {})
            )
            
            serializer = TransactionSerializer(transaction)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
            
        except TransactionFailedException as e:
            logger.error(f"Transfer failed: {e}")
            return Response(
                {
                    'error': e.__class__.__name__,
                    'message': e.message,
                    'details': e.extra
                },
                status=e.status_code
            )