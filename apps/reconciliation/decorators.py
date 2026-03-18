import logging
from functools import wraps
from django.core.cache import cache
from django.utils import timezone
from .models import ReconciliationReport

logger = logging.getLogger(__name__)

def idempotent_check(check_name):
    """
    Decorator to make reconciliation checks idempotent.
    
    Usage:
        @shared_task(bind=True)
        @idempotent_check('double_entry')
        def check_double_entry(self, report_id):
            # Your check logic
            return result
    """
    def decorator(func):
        @wraps(func)
        def wrapper(self, report_id, *args, **kwargs):
            from .models import ReconciliationReport
            
            task_key = f"reconciliation:{check_name}:{report_id}"
            
            try:
                # Check if already completed in database
                report = ReconciliationReport.objects.get(id=report_id)
                
                if report.checks_summary.get(check_name, {}).get('completed'):
                    cached_result = report.checks_summary[check_name]
                    logger.info(
                        f"[{check_name.upper()}] Already completed for report {report_id}"
                    )
                    return cached_result
                
            except ReconciliationReport.DoesNotExist:
                logger.error(f"[{check_name.upper()}] Report {report_id} not found")
                raise
            
            # Execute the check
            result = func(self, report_id, *args, **kwargs)
            
            # Mark as completed and save to database
            if result and not result.get('error'):
                result['completed'] = True
                result['completed_at'] = timezone.now().isoformat()
                
                try:
                    report.checks_summary[check_name] = result
                    report.save(update_fields=['checks_summary'])
                    logger.info(f"[{check_name.upper()}] Saved result to database")
                except Exception as e:
                    logger.error(f"[{check_name.upper()}] Failed to save: {e}")
            
            # Clear progress cache
            cache.delete(task_key)
            
            return result
        
        return wrapper
    return decorator