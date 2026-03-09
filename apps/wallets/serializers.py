"""
Serializers for wallet API endpoints.
"""
from decimal import Decimal
from rest_framework import serializers
from django.contrib.auth import get_user_model
from .models import Wallet, Transaction, LedgerEntry
from .constants import TransactionType, TransactionStatus, EntryType

User = get_user_model()

class WalletSerializer(serializers.ModelSerializer):
    """Serializer for Wallet model."""
    balance = serializers.SerializerMethodField()
    user_email = serializers.EmailField(source='user.email', read_only=True)
    
    class Meta:
        model = Wallet
        fields = [
            'id',
            'user_email',
            'currency',
            'name',
            'is_system',
            'balance',
            'created_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'balance']
    
    def get_balance(self, obj) -> Decimal:
        """Get cached balance."""
        return obj.get_balance()

class LedgerEntrySerializer(serializers.ModelSerializer):
    """Serializer for LedgerEntry model"""
    transaction_reference = serializers.CharField(source='transaction.reference', read_only=True)
    transaction_type = serializers.CharField(source='transaction.transaction_type', read_only=True)
    
    class Meta:
        model = LedgerEntry
        fields = [
            'id',
            'entry_type',
            'amount',
            'balance_after',
            'description',
            'transaction_reference',
            'transaction_type',
            'created_at'
        ]
        read_only_fields = fields
        
class TransactionSerializer(serializers.ModelSerializer):
    """Serializer for Transaction model."""
    initiated_by_email = serializers.EmailField(
        source='initiated_by.email',
        read_only=True
    )
    ledger_entries = LedgerEntrySerializer(many=True, read_only=True)
    
    class Meta:
        model = Transaction
        fields = [
            'id',
            'reference',
            'transaction_type',
            'status',
            'amount',
            'currency',
            'description',
            'metadata',
            'initiated_by_email',
            'ledger_entries',
            'created_at',
        ]
        read_only_fields = fields 
        
class DepositSerializer(serializers.Serializer):
    """Serializer for deposit requests."""
    wallet_id = serializers.UUIDField(required=True)
    amount = serializers.DecimalField(
        max_digits=20,
        decimal_places=2,
        min_value=Decimal('0.01'),
        required=True
    )
    description = serializers.CharField(
        max_length=500,
        required=False,
        allow_blank=True,
        default=''
    )
    metadata = serializers.JSONField(
        required=False,
        default=dict
    )
    
    def validate_amount(self, value):
        """Validate amount is positive"""
        if value <= 0:
            raise serializers.ValidationError("Amount must be positive")
        return value
    
class WithdrawSerializer(serializers.Serializer):
    """Serializer for withdraw request."""
    
    wallet_id = serializers.UUIDField(required=True)
    amount = serializers.DecimalField(
        max_digits=20,
        decimal_places=2,
        required=True
    )
    description = serializers.CharField(
        max_length=500,
        required=False,
        allow_blank=True,
        default=''
    )
    metadata = serializers.JSONField(
        required=False,
        default=dict
    )
    
    def validate_amount(self, value):
        """Validate amount is positive"""
        if value <= 0 :
            raise serializers.ValidationError("Amount must be positive")
        return value
    
class TransferSerializer(serializers.Serializer):
    """Serializer for transfer requests."""
    
    from_wallet_id = serializers.UUIDField(required=True)
    to_wallet_id = serializers.UUIDField(required=True)
    amount = serializers.DecimalField(
        max_digits=20,
        decimal_places=2,
        min_value=Decimal('0.01'),
        required=True
    )
    description = serializers.CharField(
        max_length=500,
        required=False,
        allow_blank=True,
        default=''
    )
    metadata = serializers.JSONField(
        required=False,
        default=dict
    )
    
    def validate(self, data):
        """Validate that from and to wallets are different."""
        if data['from_wallet_id'] == data['to_wallet_id']:
            raise serializers.ValidationError(
                "Cannot transfer to the same wallet"
            )
        return data
    
    def validate_amount(self, value):
        """Validate amount is positive."""
        if value <= 0:
            raise serializers.ValidationError("Amount must be positive")
        return value
    
class BalanceSerializer(serializers.Serializer):
    """Serializer for balance response."""
    
    wallet_id = serializers.UUIDField()
    currency = serializers.CharField()
    balance = serializers.DecimalField(max_digits=20, decimal_places=2)
    computed_balance = serializers.DecimalField(max_digits=20, decimal_places=2)
    is_consistent = serializers.BooleanField()
    last_updated = serializers.CharField()
    