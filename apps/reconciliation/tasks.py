"""Celery tasks for reconciliation"""
from django.core.cache import cache
import logging
from decimal import Decimal
import smtplib
from celery import shared_task, chord
from django.db.models import Sum, Q, Count
from django.utils import timezone
from django.conf import settings
from datetime import timedelta
from django.db.models.functions import Coalesce

from apps.wallets.models import Wallet, Transaction, LedgerEntry
from apps.wallets.constants import TransactionStatus, EntryType
from .models import ReconciliationReport,  ReconciliationStatus, ReconciliationType

from django.core.mail import send_mail
from django.template.loader import render_to_string
from celery.exceptions import SoftTimeLimitExceeded
from .decorators import idempotent_check

logger = logging.getLogger(__name__)

@shared_task(bind=True, max_retries=3)
@idempotent_check('double_entry')
def check_double_entry(self, report_id):
    """Check 1: Every completed transaction has balanced double entries.
    SUM(debits) == SUM(credits) for each transactions."""
    task_key = f"reconciliation:double_entry:{report_id}"
    try:
        # Check for cached progress
        cached_progress = cache.get(task_key)
        if cached_progress:
            logger.info(f"[Check 1] Resuming from {cached_progress['checked_count']}")
            discrepancies = cached_progress.get('discrepancies', [])
            checked_count = cached_progress.get('checked_count', 0)
        else:
            discrepancies = []
            checked_count = 0
            
        logger.info(f"[Check 1] Starting double-entry balance check for report {report_id}")
        
        discrepancies = []
        all_statuses = list(Transaction.objects.values_list('status', flat=True).distinct())
        logger.info(f"[Check 1] All statuses in database: {all_statuses}")
        
        completed_statuses = [
            s for s in all_statuses
            if s and 'complet' in s.lower()
        ]
        if not completed_statuses:
            logger.warning(f"[Check 1] No 'completed' status found! Using constant.")
            try:
                completed_statuses = [TransactionStatus.COMPLETED]
            except:
                completed_statuses = ['COMPLETED', 'Completed', 'completed']
                
        logger.info(f"[Check 1] Filtering for statuses: {completed_statuses}")
        
        # Count first
        total_count = Transaction.objects.filter(status__in=completed_statuses).count()
        logger.info(f"[Check 1] Found {total_count} completed transactions to check")
        
        if total_count == 0:
            logger.warning(f"[Check 1] No transactions found! Check status values.")
            return {
                'check': 'double_entry',
                'passed': True,
                'issues_count': 0,
                'discrepancies': [],
                'severity': 'LOW',
                'metadata': {
                    'transactions_checked': 0,
                    'all_statuses_in_db': all_statuses,
                    'completed_statuses_used': completed_statuses,
                    'warning': 'No transactions matched the completed status filter'
                }
            }
            
        # Use iterator to avoid memory over loading
        transactions = Transaction.objects.filter(
            status__in=completed_statuses
        ).annotate(
            total_debits=Sum('ledger_entries__amount', filter=Q(ledger_entries__entry_type=EntryType.DEBIT)),
            total_credits=Sum('ledger_entries__amount', filter=Q(ledger_entries__entry_type=EntryType.CREDIT)),
            entry_count=Count('ledger_entries')
        ).iterator(chunk_size=1000)
        
        checked_count = 0
            
        for txn in transactions:
            debits = txn.total_debits or Decimal('0')
            credits = txn.total_credits or Decimal('0')
            
            # Check is: Debits == Credits
            if debits != credits:
                discrepancies.append({
                    'transaction_id': str(txn.id),
                    'reference': txn.reference,
                    'type': txn.transaction_type,
                    'issue': 'IMBALANCED_ENTRIES',
                    'debits': str(debits),
                    'credits': str(credits),
                    'difference': str(debits - credits),
                    'severity': 'CRITICAL'
                })
                
                # Check 1b: Should have exactly 2 entries
                if txn.entry_count != 2:
                    discrepancies.append({
                        'transaction_id': str(txn.id),
                        'reference': txn.reference,
                        'Type': txn.transaction_type,
                        'Issue': 'INCORRECT_ENTRY_COUNT',
                        'entry_count': txn.entry_count,
                        'expected': 2,
                        'severity': 'HIGH'
                    })
                checked_count += 1
                
                # Progress logging every 10k
                if checked_count % 10000 == 0:
                    logger.info(f"[Check 1] Processed {checked_count} transactions...")
            
                        
            result = {
                'check': 'double_entry',
                'passed': len(discrepancies) == 0,
                'issues_count': len(discrepancies),
                'discrepancies': discrepancies[:100], # Limit to first 100 to avoid huge JSON
                'severity': 'CRITICAL' if discrepancies else 'LOW',
                'metadata': {
                'transactions_checked': checked_count,
                'all_statuses_in_db': all_statuses,
                'completed_statuses_used': completed_statuses
            }
            }
        logger.info(f"[Check 1] Completed. Checked {checked_count}, Issues: (len{discrepancies})")
        return result
    
    except SoftTimeLimitExceeded:
        logger.error(f"[Check 1] Task timeout after {self.time_limit}s")
        return {
            'check': 'double_entry',
            'passed': False,
            'issues_count': 0,
            'discrepancies': [],
            'severity': 'CRITICAL',
            'error': 'Task timed out - dataset too large'
        }
    
    except Exception as exc:
        logger.error(f"[Check 1] Error: {exc}", exc_info=True)
        raise self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))
        
@shared_task(bind=True, max_retries=3)
@idempotent_check('balance_drift')
def check_balance_drift(self, report_id):
    
    """
    Check 2: Cached balances match computed balances.
    """
    task_key = f"reconciliation:balance_drift:{report_id}"
    try:
        cached_progress = cache.get(task_key)
        if cached_progress:
            logger.info(f"[Check 1] Resuming from {cached_progress['checked_count']}")
            discrepancies = cached_progress.get('discrepancies', [])
            checked_count = cached_progress.get('checked_count', 0)
        else:
            discrepancies = []
            checked_count = 0
            
        logger.info(f"[Check 2] Starting balance drift check for report {report_id}")
        
        discrepancies = []
        auto_fixed = []
        BATCH_SIZE = settings.RECONCILIATION_BATCH_SIZE
        
        wallet_ids = list(Wallet.objects.filter(is_system=False).values_list('id', flat=True))
        total = len(wallet_ids)
        logger.info(f"[Check 2] Checking {total} wallets")
        
        for offset in range(0, total, BATCH_SIZE):
            batch_ids = wallet_ids[offset:offset + BATCH_SIZE]
            wallets = Wallet.objects.filter(id__in=batch_ids)
            
            for wallet in wallets:
                cached = wallet.get_balance()
                computed = wallet.compute_balance()
                
                if cached != computed:
                    diff = abs(cached - computed)
                    
                    if diff <= Decimal('0.01'):
                        # Auto-fix small drift
                        latest_entry = wallet.ledger_entries.order_by('-created_at').first()
                        if latest_entry:
                            # Use raw update to bypass save() restriction
                            LedgerEntry.objects.filter(pk=latest_entry.pk).update(
                                balance_after=computed
                            )
                            
                            auto_fixed.append({
                                'wallet_id': str(wallet.id),
                                'user': wallet.user.email if wallet.user else None,
                                'cached': str(cached),
                                'computed': str(computed),
                                'difference': str(diff),
                                'action': 'AUTO_FIXED'
                            })
                            logger.info(f"[Check 2] Auto-fixed wallet {wallet.id}: {diff}")
                    else:
                        discrepancies.append({
                            'wallet_id': str(wallet.id),
                            'user': wallet.user.email if wallet.user else None,
                            'issue': 'BALANCE_DRIFT',
                            'cached_balance': str(cached),
                            'computed_balance': str(computed),
                            'difference': str(cached - computed),
                            'severity': 'MEDIUM'
                        })
        
        result = {
            'check': 'balance_drift',
            'passed': len(discrepancies) == 0,
            'issues_count': len(discrepancies),
            'discrepancies': discrepancies,
            'severity': 'MEDIUM' if discrepancies else 'LOW',
            'metadata': {
                'wallets_checked': total,
                'auto_fixed': len(auto_fixed),
                'auto_fixed_details': auto_fixed
            }
        }
        
        logger.info(f"[Check 2] Completed. Issues: {len(discrepancies)}, Auto-fixed: {len(auto_fixed)}")
        return result
        
    except Exception as exc:
        logger.error(f"[Check 2] Error: {exc}")
        self.retry(exc=exc, countdown=60)
        
@shared_task(bind=True, max_retries=3)
def check_negative_balances(self, report_id):
    """Check 3: No non-system wallet should have negative balance."""
    task_key = f"reconciliation:negative_balance:{report_id}"
    try:
        cached_progress = cache.get(task_key)
        if cached_progress:
            logger.info(f"[Check 1] Resuming from {cached_progress['checked_count']}")
            discrepancies = cached_progress.get('discrepancies', [])
            checked_count = cached_progress.get('checked_count', 0)
        else:
            discrepancies = []
            checked_count = 0
            
        logger.info(f"[Check 3] Starting negative balance check for report {report_id}")
        
        discrepancies = []
        
        # Use aggregation for efficiency
        wallets = Wallet.objects.filter(
            is_system=False
        ).annotate(
            total_credits=Coalesce(
                Sum('ledger_entries__amount', filter=Q(ledger_entries__entry_type=EntryType.CREDIT)),
                Decimal('0')
            ),
            total_debits=Coalesce(
                Sum('ledger_entries__amount', filter=Q(ledger_entries__entry_type=EntryType.DEBIT)),
                Decimal('0')
            )
        )
        
        total = wallets.count()
        logger.info(f"[Check 3] Checking {total} wallets")
        
        for wallet in wallets:
            # Use the annotated values
            balance = wallet.total_credits - wallet.total_debits
            
            if balance < Decimal('0'):
                discrepancies.append({
                    'wallet_id': str(wallet.id),
                    'user': wallet.user.email if wallet.user else None,
                    'issue': 'NEGATIVE_BALANCE',
                    'balance': str(balance),
                    'severity': 'HIGH'
                })
        
        result = {
            'check': 'negative_balances',
            'passed': len(discrepancies) == 0,
            'issues_count': len(discrepancies),
            'discrepancies': discrepancies,
            'severity': 'HIGH' if discrepancies else 'LOW',
            'metadata': {
                'wallets_checked': total
            }
        }
        
        logger.info(f"[Check 3] Completed. Issues: {len(discrepancies)}")
        return result
        
    except Exception as exc:
        logger.error(f"[Check 3] Error: {exc}")
        self.retry(exc=exc, countdown=60)
        
@shared_task(bind=True, max_retries=3)
def check_transaction_state(self, report_id):
    """
    Check 4: Transaction state consistency.
    - COMPLETED transactions have exactly 2 entries
    - PENDING transactions older than 5 minutes are flagged
    - FAILED transactions have 0 entries
    """
    task_key = f"reconciliation:transaction_state:{report_id}"
    try:
        cached_progress = cache.get(task_key)
        if cached_progress:
            logger.info(f"[Check 1] Resuming from {cached_progress['checked_count']}")
            discrepancies = cached_progress.get('discrepancies', [])
            checked_count = cached_progress.get('checked_count', 0)
        else:
            discrepancies = []
            checked_count = 0
            
        logger.info(f"[Check 4] Starting transaction state check for report {report_id}")
        
        discrepancies = []
        
        # Check 4a: FAILED transactions should have 0 entries
        failed_with_entries = Transaction.objects.filter(
            status=TransactionStatus.FAILED
        ).annotate(
            entry_count=Count('ledger_entries')
        ).exclude(entry_count=0)
        
        for txn in failed_with_entries:
            discrepancies.append({
                'transaction_id': str(txn.id),
                'reference': txn.reference,
                'issue': 'FAILED_WITH_ENTRIES',
                'status': txn.status,
                'entry_count': txn.entry_count,
                'severity': 'HIGH'
            })
        
        # Check 4b: PENDING transactions older than 5 minutes
        five_mins_ago = timezone.now() - timedelta(minutes=5)
        stuck_pending = Transaction.objects.filter(
            status=TransactionStatus.PENDING,
            created_at__lt=five_mins_ago  
        )
        
        for txn in stuck_pending:
            age_minutes = int((timezone.now() - txn.created_at).total_seconds() / 60)
            discrepancies.append({
                'transaction_id': str(txn.id),
                'reference': txn.reference,
                'issue': 'STUCK_PENDING',
                'status': txn.status,
                'age_minutes': age_minutes,
                'severity': 'MEDIUM'
            })
        
        # Check 4c: COMPLETED transactions should have exactly 2 entries
        completed_wrong_entries = Transaction.objects.filter(
            status=TransactionStatus.COMPLETED
        ).annotate(
            entry_count=Count('ledger_entries')
        ).exclude(entry_count=2)
        
        for txn in completed_wrong_entries:
            discrepancies.append({
                'transaction_id': str(txn.id),
                'reference': txn.reference,
                'issue': 'WRONG_ENTRY_COUNT',
                'status': txn.status,
                'entry_count': txn.entry_count,
                'expected': 2,
                'severity': 'HIGH'
            })
        
        result = {
            'check': 'transaction_state',
            'passed': len(discrepancies) == 0,
            'issues_count': len(discrepancies),
            'discrepancies': discrepancies,
            'severity': 'MEDIUM' if discrepancies else 'LOW',
            'metadata': {
                'failed_checked': failed_with_entries.count(),
                'pending_checked': stuck_pending.count(),
                'completed_checked': completed_wrong_entries.count()
            }
        }
        
        logger.info(f"[Check 4] Completed. Issues: {len(discrepancies)}")
        return result
        
    except Exception as exc:
        logger.error(f"[Check 4] Error: {exc}")
        self.retry(exc=exc, countdown=60)

@shared_task(bind=True, max_retries=3)
def check_global_balance(self, report_id):
    """
    Check 5: System-wide balance check.
    SUM(all debits) == SUM(all credits) across entire system.
    """
    task_key = f"reconciliation:global_balance:{report_id}"
    try:
        cached_progress = cache.get(task_key)
        if cached_progress:
            logger.info(f"[Check 1] Resuming from {cached_progress['checked_count']}")
            discrepancies = cached_progress.get('discrepancies', [])
            checked_count = cached_progress.get('checked_count', 0)
        else:
            discrepancies = []
            checked_count = 0
            
        logger.info(f"[Check 5] Starting global balance check for report {report_id}")
        
        # Global aggregation with Coalesce to handle NULL
        totals = LedgerEntry.objects.aggregate(
            total_debits=Coalesce(
                Sum('amount', filter=Q(entry_type=EntryType.DEBIT)),
                Decimal('0')
            ),
            total_credits=Coalesce(
                Sum('amount', filter=Q(entry_type=EntryType.CREDIT)),
                Decimal('0')
            )
        )
        
        debits = totals['total_debits']
        credits = totals['total_credits']
        difference = debits - credits
        
        discrepancies = []
        if difference != Decimal('0'):
            discrepancies.append({
                'issue': 'GLOBAL_IMBALANCE',
                'total_debits': str(debits),
                'total_credits': str(credits),
                'difference': str(difference),
                'severity': 'CRITICAL'
            })
        
        result = {
            'check': 'global_balance',
            'passed': difference == Decimal('0'),
            'issues_count': len(discrepancies),
            'discrepancies': discrepancies,
            'severity': 'CRITICAL' if discrepancies else 'LOW',
            'metadata': {
                'total_debits': str(debits),
                'total_credits': str(credits),
                'platform_balance': str(difference)
            }
        }
        
        logger.info(f"[Check 5] Completed. Debits: {debits}, Credits: {credits}, Diff: {difference}")
        return result
        
    except Exception as exc:
        logger.error(f"[Check 5] Error: {exc}")
        self.retry(exc=exc, countdown=60)
        
@shared_task
def aggregate_results(check_results, report_id):
    """
    Callback task that aggregates results from all parallel checks.
    Updates the reconciliation report with final status.
    """
    logger.info(f"[Aggregator] Aggregating results for report {report_id}")
    
    try:
        report = ReconciliationReport.objects.get(id=report_id)
        
        # Aggregate results
        total_issues = sum(r.get('issues_count', 0) for r in check_results)
        all_passed = all(r.get('passed', False) for r in check_results)
        
        # Determine overall status based on severity
        severities = [r.get('severity', 'LOW') for r in check_results]
        if 'CRITICAL' in severities:
            status = ReconciliationStatus.CRITICAL
        elif 'HIGH' in severities:
            status = ReconciliationStatus.FAILED
        elif 'MEDIUM' in severities:
            status = ReconciliationStatus.WARNING
        else:
            status = ReconciliationStatus.PASSED
        
        # Collect all discrepancies
        all_discrepancies = []
        checks_summary = {}
        
        for result in check_results:
            check_name = result.get('check', 'unknown')
            checks_summary[check_name] = {
                'passed': result.get('passed', False),
                'issues': result.get('issues_count', 0),
                'severity': result.get('severity', 'LOW')
            }
            
            for disc in result.get('discrepancies', []):
                disc['check'] = check_name
                all_discrepancies.append(disc)
        
        # Collect statistics
        statistics = {
            'total_wallets': Wallet.objects.count(),
            'total_transactions': Transaction.objects.count(),
            'total_ledger_entries': LedgerEntry.objects.count(),
        }
        
        # Add metadata from checks
        for result in check_results:
            check_name = result.get('check', 'unknown')
            metadata = result.get('metadata', {})
            for key, value in metadata.items():
                statistics[f"{check_name}_{key}"] = value
        
        # Update report
        report.status = status
        report.completed_at = timezone.now()
        report.duration_seconds = (report.completed_at - report.started_at).total_seconds()
        report.checks_summary = checks_summary
        report.discrepancies = all_discrepancies
        report.statistics = statistics
        report.save()
        
        logger.info(
            f"[Aggregator] Report {report_id} completed. "
            f"Status: {status}, Issues: {total_issues}, Duration: {report.duration_seconds:.2f}s"
        )
        
        # Send alert if issues found
        if status in [ReconciliationStatus.CRITICAL, ReconciliationStatus.FAILED, ReconciliationStatus.WARNING]:
            send_reconciliation_alert.delay(str(report_id))
        
        return str(report_id)
        
    except Exception as exc:
        logger.error(f"[Aggregator] Error: {exc}")
        # Don't retry aggregator - just log the error
        return None
    
@shared_task
def send_reconciliation_alert(self, report_id):
    """Send email alert for reconciliation issues."""
    try:
        report = ReconciliationReport.objects.get(id=report_id)
        subject = f"[{report.status}] Reconciliation Report - {report.started_at.strftime('%Y-%M-%D')}"
        
        # Email body
        message = f"""
Reconciliation Report
=====================

Status: {report.status}
Started: {report.started_at}
Completed: {report.completed_at}
Duration: {report.duration_seconds:.2f} seconds

Issues Found: {report.total_issues}

Checks Summary:
{'-' * 50}
"""

        for check, summary in report.checks_summary.items():
            message += f"\n{check}: {'PASSED' if summary['passed'] else 'FAILED'} ({summary['issues']} issues)"
            
        if report.discrepancies:
            message += f"\n\nDiscrepancies:\n{'_' * 50}\n"
            for disc in report.discrepancies[:10]: # first 10
                message += f"\n- {disc.get('issue', 'Unknown')}: {disc}"
                
            if len(report.discrepancies) > 10:
                message += f"\n\n... and {len(report.discrepancies) - 10} more issues"
        
        message += f"\n\nView full report: {settings.SITE_URL}/api/v1/reconciliation/reports/{report_id}/"
                    
        # Send email
        send_mail(
            subject=subject,
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=settings.RECONCILIATION_ALERT_EMAILS,
            fail_silently=False,
        )
        logger.info(f"[Alert] Sent email for report {report_id}")
        
    except smtplib.SMTPException as exc:
        logger.error(f"[Alert] Email failed: {exc}")
        # Retry email sending
        raise self.retry(exc=exc, countdown=300, max_retries=3)  # Retry after 5 min
        
    except ReconciliationReport.DoesNotExist:
        logger.error(f"[Alert] Report {report_id} not found")
        # Don't retry - report doesn't exist
        
    except Exception as exc:
        logger.error(f"[Alert] Unexpected error: {exc}", exc_info=True)
        # Don't retry unexpected errors

@shared_task
def run_reconciliation(run_type: str = 'SCHEDULED', report_id=None):
    """Master task that orchestrates the entire reconciliation process.
    Run 5 checks in parallel using Celery chord."""
    
    # Validate run_type early
    valid_types = [choice[0] for choice in ReconciliationType.choices]
    if run_type not in valid_types:
        error_msg = f"Invalid run_type: '{run_type}'. Must be one of {valid_types}"
        logger.error(f"[Master] {error_msg}")
        raise ValueError(error_msg)
    
    logger.info(f"[Master] Starting {run_type} reconciliation for report {report_id}")
    
    try:
        # Create report if not provided
        if report_id is None:
            report = ReconciliationReport.objects.create(
                run_type=run_type,
                status=ReconciliationStatus.RUNNING,
                started_at=timezone.now()
            )
            report_id = str(report.id)
            logger.info(f"[Master] Created report {report_id}")
        else:
            # Update existing report to RUNNING
            report = ReconciliationReport.objects.get(id=report_id)
            report.status = ReconciliationStatus.RUNNING
            report.started_at = timezone.now()
            report.save()
            logger.info(f"[Master] Updated report {report_id} to RUNNING")
            
        # Define parallel workflow using chord
        workflow = chord([
            check_double_entry.s(report_id),
            check_balance_drift.s(report_id),
            check_negative_balances.s(report_id),
            check_transaction_state.s(report_id),
            check_global_balance.s(report_id)
        ])(aggregate_results.s(report_id))
        
        logger.info(f"[Master] Workflow started for report {report_id}")
        return report_id
    
    except ReconciliationReport.DoesNotExist:
        error_msg = f"Report {report_id} not found"
        logger.error(f"[Master] {error_msg}")
        raise
    
    except Exception as exc:
        logger.error(f"[Master] Error starting reconciliation: {exc}", exc_info=True)
        if report_id:
            try:
                report = ReconciliationReport.objects.get(id=report_id)
                report.status = ReconciliationStatus.FAILED
                report.completed_at = timezone.now()
                report.save()
                logger.info(f"[Master] Marked report {report_id} as FAILED")
            except Exception as e:
                logger.error(f"[Master] Failed to update report status: {e}")
        raise