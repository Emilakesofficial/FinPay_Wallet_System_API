"""
Constants for the wallet system.
"""
from django.db import models

class TransactionType(models.TextChoices):
    """Types of transactions."""
    DEPOSIT = 'DEPOSIT', 'Deposit'
    WITHDRAWAL = 'WITHDRAWAL', 'Withdrawal'
    TRANSFER = 'TRANSFER', 'Transfer'
    
class TransactionStatus(models.TextChoices):
    """Status of a transaction."""
    PENDING = 'PENDING', 'Pending'
    COMPLETED = 'COMPLETED', 'Completed'
    FAILED = 'FAILED', 'Failed'

class EntryType(models.TextChoices):
    """Double-entry bookkeeping entry types."""
    DEBIT = 'DEBIT', 'Debit'
    CREDIT = 'CREDIT', 'Credit'