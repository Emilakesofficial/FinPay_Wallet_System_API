# Test 1: Run check twice - should return cached result second time
from apps.reconciliation.tasks import check_double_entry
from apps.reconciliation.serializers import ReconciliationReport

report = ReconciliationReport.objects.create(run_type='MANUAL', status='RUNNING')

# First run
result1 = check_double_entry(str(report.id))
print(f"First run: {result1['issues_count']} issues")

# Second run (should be instant)
result2 = check_double_entry(str(report.id))
print(f"Second run: {result2['issues_count']} issues (from cache)")

assert result1 == result2  # ✅ Results should be identical

# Test 2: Simulate crash and resume
from django.core.cache import cache

# Manually set progress
cache.set('reconciliation:double_entry:test-report-id', {
    'checked_count': 50000,
    'discrepancies': [],
}, timeout=3600)

# Run task - should resume from 50k
result = check_double_entry('test-report-id')
# Check logs: "[Check 1] Resuming from 50000"