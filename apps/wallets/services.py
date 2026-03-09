"""
Core wallet service implementing all business logic for money operations.

CRITICAL RULES:
1. All operations are atomic (wrapped in transactions)
2. Pessimistic locking on wallets (SELECT FOR UPDATE)
3. Idempotency is enforced on all mutations
4. Double-entry bookkeeping is strictly maintained
5. Every transaction creates exactly 2 ledger entries
"""

import logging 
import structlog
from decimal import Decimal
from typing import Optional, Dict, Any
from django.db import IntegrityError, transaction
from django.db.models import F
from django.conf import settings
from django.contrib.auth import get_user_model
import traceback

from .models import Wallet, Transaction, LedgerEntry
from .constants import TransactionType, TransactionStatus, EntryType
from common.exceptions import (
    InsufficientFundsException,
    InvalidAmountException,
    TransactionNotFoundException, 
    WalletNotFoundException,
    DuplicateTransactionException,
    TransactionFailedException
)
from common.utils import normalize_amount, generate_reference
from apps.audit.service import AuditService

User = get_user_model()
logger = structlog.getLogger(__name__)

class WalletService:
    """
    Service class handling all wallet operations.
    This is the ONLY place where money moves.
    """
    
    @staticmethod
    def _get_system_wallet() -> Wallet:
        """
        Get or create the system wallet.
        Returns:
            Wallet: The system wallet
        Raises:
            WalletNotFoundException: If system wallet doesn't exist
        """
        try:
            return Wallet.objects.select_for_update().get(
                is_system=True,
                currency=settings.WALLET_CURRENCY
            )
        except Wallet.DoesNotExist:
            raise WalletNotFoundException(
                "System wallet not found. Run 'create_system_wallet' command",
                code='system_wallet_missing'
            )
        except Wallet.MultipleObjectsReturned:
            logger.error("Multiple system wallets found - database integrity issue")
            # Return first one but log error - this should never happen
            return Wallet.objects.select_for_update().filter(
                is_system=True,
                currency=settings.WALLET_CURRENCY
            ).first()
        
    @staticmethod
    def _validate_amount(amount: Any) -> Decimal:
        """
        Validate and normalize an amount.
        Args:
            amount: Amount to validate
        Returns:
            Decimal: Normalized amount
        Raises:
            InvalidAmountException: If amount is invalid
        """
        
        try:
            return normalize_amount(amount)
        except ValueError as e:
            logger.warning(f"Invalid amount", amount=str(amount), error=str(e))
            raise InvalidAmountException(str(e), amount=str(amount))
        
    @staticmethod
    def _check_idempotency(idempotency_key: str) -> Optional[Transaction]:
        """
        Check if a transaction with this idempotency key already exists.
        Args:
            idempotency_key: The idempotency key to check
        Returns:
            Optional[Transaction]: Existing transaction if found, None otherwise
        Raises:
            DuplicateTransactionException: If transaction exists but is still pending
        """
        try:
            existing_txn = Transaction.objects.get(idempotency_key=idempotency_key)
            
            if existing_txn.status:
                logger.info(
                    "returning_existing_transaction",
                    transaction_id=str(existing_txn.id),
                    idempotency_key=idempotency_key
                )
                return existing_txn   
        except Transaction.DoesNotExist:
            return None
        
    @staticmethod
    def _create_ledger_entries(
        transaction: Transaction,
        debit_wallet: Wallet,
        credit_wallet: Wallet,
        amount: Decimal,
        description: str = ""
    ) -> tuple[LedgerEntry, LedgerEntry]:
        """
        Create a pair of ledger entries (debit and credit) for double-entry bookkeeping.
        Args:
            transaction: The transaction these entries belong to
            debit_wallet: Wallet to debit
            credit_wallet: Wallet to credit
            amount: Amount to transfer
            description: Description for the entries
        Returns:
            tuple: (debit_entry, credit_entry)
        """
        # Lock both wallets and get their current balances
        # Order by ID to prevent deadlocks
        wallet_ids = sorted([debit_wallet.id, credit_wallet.id])
        locked_wallets = {
            w.id: w for w in Wallet.objects.filter(id__in=wallet_ids).select_for_update().order_by('id')
        }
        
        debit_wallet = locked_wallets[debit_wallet.id]
        credit_wallet = locked_wallets[credit_wallet.id]
        
        # Deterministic balances (aggregate), safe even if created_at ties
        debit_before = debit_wallet.compute_balance()
        credit_before = credit_wallet.compute_balance()

        # Calculate new balance
        debit_after = debit_before - amount
        credit_after = credit_before + amount
        
        # Create debit entry
        debit_entry = LedgerEntry.objects.create(
            wallet=debit_wallet,
            transaction=transaction,
            entry_type=EntryType.DEBIT,
            amount=amount,
            balance_after=debit_after,
            description=description or f"Debit for {transaction.reference}"
        )
        
        # Create credit entry
        credit_entry = LedgerEntry.objects.create(
            wallet=credit_wallet,
            transaction=transaction,
            entry_type=EntryType.CREDIT,
            amount=amount,
            balance_after=credit_after,
            description=description or f"Debit for {transaction.reference}"
        )
        logger.info(
            "ledger_entries_created",
            transaction_id=str(transaction.id),
            debit_wallet=str(debit_wallet.id),
            credit_wallet=str(credit_wallet.id),
            amount=str(amount)
        )
        return debit_entry, credit_entry
    
    @staticmethod
    @transaction.atomic
    def deposit(
        wallet_id: str,
        amount: Any,
        idempotency_key: str,
        initiated_by: Optional[User] = None, # type: ignore
        description: str = "",
        metadata: Optional[Dict[str, Any]] = None
    ) -> Transaction:
        """
        Deposit money into a wallet.
        Double-entry:
        - DEBIT system wallet (asset increases)
        - CREDIT user wallet (liability increases)
        Args:
            wallet_id: UUID of the wallet to deposit into
            amount: Amount to deposit
            idempotency_key: Unique key to prevent duplicate deposits
            initiated_by: User who initiated the deposit
            description: Description of the deposit
            metadata: Additional metadata
        Returns:
            Transaction: The completed deposit transaction
        Raises:
            WalletNotFoundException: If wallet not found
            InvalidAmountException: If amount is invalid
            DuplicateTransactionException: If idempotency key already used
        """
        
        # Validate amount
        amount = WalletService._validate_amount(amount)
        
        # Lock wallet(s)
        user_wallet = Wallet.objects.select_for_update().get(id=wallet_id)
        system_wallet = WalletService._get_system_wallet()

        txn, created = WalletService._get_or_create_transaction(
            idempotency_key=idempotency_key,
            defaults=dict(
                transaction_type=TransactionType.DEPOSIT,
                status=TransactionStatus.PENDING,
                amount=amount,
                currency=user_wallet.currency,
                reference=generate_reference("DEP"),
                description=description or f"Deposit to {user_wallet.name}",
                metadata=metadata or {},
                initiated_by=initiated_by,
            )
        )
        if not created:
            return txn

        # Create ledger entries (double-entry bookkeeping)
        try:
            WalletService._create_ledger_entries(
                transaction=txn,
                debit_wallet=system_wallet,
                credit_wallet=user_wallet,
                amount=amount,
                description=f"Deposit: {description}" if description else None
            )
            
            # Mark transaction as completed
            txn.status = TransactionStatus.COMPLETED
            txn.save(update_fields=['status'])
            
            # Audit log
            AuditService.log_deposit(txn, initiated_by)
            
            logger.info(
                "deposit_completed",
                transaction_id=str(txn.id),
                wallet_id=wallet_id,
                amount=str(amount)
            )
            
            return txn
        
        except Exception as e:
            # Mark transaction as failed
            txn.status = TransactionStatus.FAILED
            txn.save(update_fields=['status'])
            logger.exception(
                "deposit_failed",
                transaction_id=str(txn.id),
                wallet_id=wallet_id,
                error=str(e)
            )
            
            raise TransactionFailedException(
                "Deposit failed",
                transaction_id=str(txn.id),
                original_error=str(e)
            )
    
    @staticmethod
    @transaction.atomic
    def withdraw(
        wallet_id: str,
        amount: Any,
        idempotency_key: str,
        initiated_by: Optional[User] = None, # type: ignore
        description: str = "",
        metadata: Optional[Dict[str, Any]] = None
    ) -> Transaction:
        """
        Withdraw money from a wallet.
        
        Double-entry:
        - DEBIT user wallet (liability decreases)
        - CREDIT system wallet (asset decreases)
        
        Args:
            wallet_id: UUID of the wallet to withdraw from
            amount: Amount to withdraw
            idempotency_key: Unique key to prevent duplicate withdrawals
            initiated_by: User who initiated the withdrawal
            description: Description of the withdrawal
            metadata: Additional metadata
        
        Returns:
            Transaction: The completed withdrawal transaction
        
        Raises:
            WalletNotFoundException: If wallet not found
            InvalidAmountException: If amount is invalid
            InsufficientFundsException: If wallet has insufficient balance
            DuplicateTransactionException: If idempotency key already used
        """
        
        # Check idempotency
        existing_txn = WalletService._check_idempotency(idempotency_key)
        if existing_txn:
            return existing_txn
            
        # Validate amount
        amount = WalletService._validate_amount(amount)
        
        # Get wallets with lock
        try:
            user_wallet = Wallet.objects.select_for_update().get(id=wallet_id)
        except Wallet.DoesNotExist:
            logger.error(f"Wallet not found: {wallet_id}")
            raise WalletNotFoundException(f"Wallet {wallet_id} not found")
        
        # Check sufficient balance
        current_balance = user_wallet.get_balance()
        if current_balance < amount:
            logger.warning(
                "insufficient_funds",
                wallet_id=wallet_id,
                balance=str(current_balance),
                requested=str(amount),
                shortfall=str(amount - current_balance)
            )
            raise InsufficientFundsException(
                f"Insufficient funds",
                wallet_id=wallet_id,
                balance=str(current_balance),
                required=str(amount),
                shortfall=str(amount - current_balance)
            )
            
        system_wallet = WalletService._get_system_wallet()
        
        # Create transaction
        txn = Transaction.objects.create(
            idempotency_key=idempotency_key,
            transaction_type=TransactionType.WITHDRAWAL,
            status=TransactionStatus.PENDING,
            amount=amount,
            currency=user_wallet.currency,
            reference=generate_reference("WTH"),
            description=description or f"Withdrawal from {user_wallet.name}",
            metadata=metadata or {},
            initiated_by=initiated_by
        )
        logger.info(f"Created withdrawal transaction: {txn.id} for {amount} from wallet {wallet_id}")
        
        # Create ledger entries (double-entry bookkeeping)
        try:
            
            WalletService._create_ledger_entries(
                    transaction=txn,
                    debit_wallet=user_wallet,
                    credit_wallet=system_wallet,
                    amount=amount,
                    description=f"Withdrawal: {description}" if description else None
            )

            # Mark transaction as completed
            txn.status = TransactionStatus.COMPLETED
            txn.save(update_fields=['status'])
            
            #Audit log
            AuditService.log_withdrawal(txn, initiated_by)
            
            logger.info(
                "withdrawal_completed",
                transaction_id=str(txn.id),
                wallet_id=wallet_id,
                amount=str(amount),
                new_balance=str(user_wallet.get_balance())
            )
            return txn
        except Exception as e:
            # Mark transaction as failed
            txn.status = TransactionStatus.FAILED
            txn.save(update_fields=['status'])
            logger.exception(
                "withdrawal_failed",
                transaction_id=str(txn.id),
                wallet_id=wallet_id,
                error=str(e)
            )
            
            raise TransactionFailedException(
                "Withdrawal failed",
                transaction_id=str(txn.id),
                original_error=str(e)
            )
    
    @staticmethod
    @transaction.atomic
    def transfer(
        from_wallet_id: str,
        to_wallet_id: str,
        amount: Any,
        idempotency_key: str,
        initiated_by: Optional[User] = None, # type: ignore
        description: str = "",
        metadata: Optional[Dict[str, Any]] = None
    ) -> Transaction:
        """
        Transfer money from one wallet to another.
        
        Double-entry:
        - DEBIT sender wallet (their balance decreases)
        - CREDIT receiver wallet (their balance increases)
        
        Args:
            from_wallet_id: UUID of the sender wallet
            to_wallet_id: UUID of the receiver wallet
            amount: Amount to transfer
            idempotency_key: Unique key to prevent duplicate transfers
            initiated_by: User who initiated the transfer
            description: Description of the transfer
            metadata: Additional metadata
        
        Returns:
            Transaction: The completed transfer transaction
        
        Raises:
            WalletNotFoundException: If either wallet not found
            InvalidAmountException: If amount is invalid
            InsufficientFundsException: If sender has insufficient balance
            DuplicateTransactionException: If idempotency key already used
            ValueError: If trying to transfer to the same wallet
        """
        # Check idempotency
        existing_txn = WalletService._check_idempotency(idempotency_key)
        if existing_txn:
            return existing_txn
        
        # Validate same wallet
        if from_wallet_id == to_wallet_id:
            raise InvalidAmountException("Cannot transfer to the same wallet")
        
        # Validate amount
        amount = WalletService._validate_amount(amount)
        
        # Get wallets with lock (ordered to prevent deadlock)
        wallet_ids = sorted([from_wallet_id, to_wallet_id])
        try:
            locked_wallets = {
                str(w.id): w 
                for w in Wallet.objects.filter(id__in=wallet_ids).select_for_update().order_by('id')
            }
        except Exception as e:
            logger.error(f"Failed to lock wallets: {e}")
            raise WalletNotFoundException("One or both wallets not found")
        
        if len(locked_wallets) != 2:
            missing = set([from_wallet_id, to_wallet_id]) - set(locked_wallets.keys())
            logger.error(f"Wallets not found: {missing}")
            raise WalletNotFoundException(f"Wallets not found: {missing}")
        
        from_wallet = locked_wallets[from_wallet_id]
        to_wallet = locked_wallets[to_wallet_id]
        
        # Check currency match
        if from_wallet.currency != to_wallet.currency:
            logger.warning(
                "currency_mismatch",
                from_currency=from_wallet.currency,
                to_currency=to_wallet.currency
            )
            raise InvalidAmountException(
                f"Currency mismatch",
                from_currency=from_wallet.currency,
                to_currency=to_wallet.currency
            )
            
        # Check sufficient balance
        current_balance = from_wallet.get_balance()
        if current_balance < amount:
            logger.warning(
                "insufficient_funds_for_transfer",
                from_wallet_id=from_wallet_id,
                balance=str(current_balance),
                requested=str(amount)
            )
            raise InsufficientFundsException(
                f"Insufficient funds for transfer",
                wallet_id=from_wallet_id,
                balance=str(current_balance),
                required=str(amount),
                shortfall=str(amount - current_balance)
            )
            
        # Create transaction
        txn = Transaction.objects.create(
            idempotency_key=idempotency_key,
            transaction_type=TransactionType.TRANSFER,
            status=TransactionStatus.PENDING,
            amount=amount,
            currency=from_wallet.currency,
            reference=generate_reference("TRF"),
            description=description or f"Transfer from {from_wallet.name} to {to_wallet.name}",
            metadata={
                **(metadata or {}),
                'from_wallet_id': str(from_wallet_id),
                'to_wallet_id': str(to_wallet_id)
            },
            initiated_by=initiated_by
        )
        logger.info(
            f"Created transfer transaction: {txn.id} for {amount} "
            f"from {from_wallet_id} to {to_wallet_id}"
        )
        
        # Create ledger entries (double-entry bookkeeping)
        try:
            WalletService._create_ledger_entries(
                transaction=txn,
                debit_wallet=from_wallet,
                credit_wallet=to_wallet,
                amount=amount,
                description=f"Transfer: {description}" if description else None
            )
        # Mark transaction as completed
            txn.status = TransactionStatus.COMPLETED
            txn.save(update_fields=['status'])
            
            # Audit log
            AuditService.log_transfer(txn, initiated_by)
            
            logger.info(
                "transfer_completed",
                transaction_id=str(txn.id),
                from_wallet_id=from_wallet_id,
                to_wallet_id=to_wallet_id,
                amount=str(amount)
            )
            
            return txn 
        
        except Exception as e:
            # Mark transaction as failed
            txn.status = TransactionStatus.FAILED
            txn.save(update_fields=['status'])
            
            logger.exception(
                "transfer_failed",
                transaction_id=str(txn.id),
                from_wallet_id=from_wallet_id,
                to_wallet_id=to_wallet_id,
                error=str(e)
            )
            
            raise TransactionFailedException(
                "Transfer failed",
                transaction_id=str(txn.id),
                original_error=str(e)
            )
        
    @staticmethod
    def get_balance(wallet_id: str) -> Dict[str, Any]:
        """
        Get the balance of a wallet.
        
        Returns both the cached balance (from latest ledger entry) and
        the computed balance (from summing all entries) for verification.
        
        Args:
            wallet_id: UUID of the wallet
        
        Returns:
            dict: Balance information
        
        Raises:
            WalletNotFoundException: If wallet not found
        """
        
        try:
            wallet = Wallet.objects.get(id=wallet_id)
        except Wallet.DoesNotExist:
            logger.error(f"Wallet not found: {wallet_id}")
            raise WalletNotFoundException(f"Wallet {wallet_id} not found")
        
        cached_balance = wallet.get_balance()
        computed_balance = wallet.compute_balance()
        
        # Flag if there's a discrepancy
        is_consistent = cached_balance == computed_balance
        
        if not is_consistent:
            logger.error(
                "balance_inconsistency_detected",
                wallet_id=wallet_id,
                cached_balance=str(cached_balance),
                computed=str(computed_balance),
                difference=str(cached_balance - computed_balance)
            )
        
        return {
            'wallet_id': str(wallet.id),
            'currency': wallet.currency,
            'balance': str(cached_balance),
            'computed_balance': str(computed_balance),
            'is_consistent': is_consistent,
            'last_updated': wallet.updated_at.isoformat()
        }
        
    @staticmethod
    def _get_or_create_transaction(*, idempotency_key, defaults) -> tuple[Transaction, bool]:
        """
        Concurrency-safe idempotency claim:
        - created=True: caller owns this idempotency key, proceed to ledger write
        - created=False: return existing transaction, do NOT write ledger again
        """
        return Transaction.objects.get_or_create(
            idempotency_key=idempotency_key,
            defaults=defaults,
        )