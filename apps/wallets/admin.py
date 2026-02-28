"""
Admin configuration for wallets app.
"""
from django.contrib import admin
from django.utils.html import format_html
from .models import Wallet, Transaction, LedgerEntry


@admin.register(Wallet)
class WalletAdmin(admin.ModelAdmin):
    """Admin interface for Wallet model."""
    list_display = ['id', 'user_email', 'currency', 'is_system', 'current_balance', 'created_at']
    list_filter = ['is_system', 'currency', 'created_at']
    search_fields = ['id', 'user__email', 'name']
    readonly_fields = ['id', 'created_at',  'current_balance', 'computed_balance']
    
    def user_email(self, obj):
        return obj.user.email if obj.user else 'N/A (System)'
    user_email.short_description = 'User'
    
    def current_balance(self, obj):
        balance = obj.get_balance()
        color = 'green' if balance >= 0 else 'red'
        return format_html(
            '<span style="color: {};">{}</span>',
            color,
            balance
        )
    current_balance.short_description = 'Balance (Cached)'
    
    def computed_balance(self, obj):
        balance = obj.compute_balance()
        color = 'green' if balance >= 0 else 'red'
        return format_html(
            '<span style="color: {};">{}</span>',
            color,
            balance
        )
    computed_balance.short_description = 'Balance (Computed)'


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    """Admin interface for Transaction model."""
    list_display = ['reference', 'transaction_type', 'amount', 'currency', 'status', 'created_at']
    list_filter = ['transaction_type', 'status', 'created_at']
    search_fields = ['reference', 'idempotency_key', 'description']
    readonly_fields = ['id', 'created_at']
    
    def has_delete_permission(self, request, obj=None):
        # Prevent deletion of transactions
        return False


@admin.register(LedgerEntry)
class LedgerEntryAdmin(admin.ModelAdmin):
    """Admin interface for LedgerEntry model."""
    list_display = ['id', 'wallet', 'transaction_ref', 'entry_type', 'amount', 'balance_after', 'created_at']
    list_filter = ['entry_type', 'created_at']
    search_fields = ['wallet__user__email', 'transaction__reference']
    readonly_fields = ['id', 'created_at']
    
    def transaction_ref(self, obj):
        return obj.transaction.reference
    transaction_ref.short_description = 'Transaction'
    
    def has_delete_permission(self, request, obj=None):
        # Prevent deletion of ledger entries
        return False
    
    def has_change_permission(self, request, obj=None):
        # Prevent modification of ledger entries
        return False