import pytest


def test_aggregate_results_updates_report(db, monkeypatch):
    """aggregate_results should update the ReconciliationReport based on check results."""
    from apps.reconciliation import tasks
    from apps.reconciliation.models import ReconciliationReport, ReconciliationStatus

    # Create an empty report
    report = ReconciliationReport.objects.create()
    report_id = str(report.id)

    # Prepare sample check results with a CRITICAL severity to force that status
    check_results = [
        {
            'check': 'double_entry',
            'passed': False,
            'issues_count': 1,
            'severity': 'CRITICAL',
            'discrepancies': [
                {'issue': 'GLOBAL_IMBALANCE', 'details': 'imbalance'}
            ],
            'metadata': {}
        },
        {
            'check': 'balance_drift',
            'passed': True,
            'issues_count': 0,
            'severity': 'LOW',
            'discrepancies': [],
            'metadata': {}
        }
    ]

    # Patch out the alert sender to avoid side effects
    class DummyAlert:
        def delay(self, *_args, **_kw):
            return None

    monkeypatch.setattr(tasks, 'send_reconciliation_alert', DummyAlert())

    # Call the aggregator synchronously
    tasks.aggregate_results(check_results, report_id)

    # Refresh and assert
    report.refresh_from_db()
    assert report.status == ReconciliationStatus.CRITICAL
    assert report.total_issues == 1
    assert 'double_entry' in report.checks_summary


def test_run_reconciliation_creates_report_and_invokes_chord(db, monkeypatch):
    """run_reconciliation should create a ReconciliationReport and start the Celery chord workflow.

    We patch `chord` to capture the task signatures passed in and avoid starting real Celery workers.
    """
    from apps.reconciliation import tasks
    from apps.reconciliation.models import ReconciliationReport, ReconciliationStatus

    captured = {}

    def fake_chord(sigs):
        # capture the list of signatures passed to chord
        captured['sigs'] = sigs

        class Runner:
            def __call__(self, _agg_sig):
                # Do nothing (simulate immediate scheduling)
                return None

        return Runner()

    monkeypatch.setattr(tasks, 'chord', fake_chord)

    # Run reconciliation (should create a report and call our fake_chord)
    report_id = tasks.run_reconciliation(run_type='TEST')

    # Assert a report was created
    assert ReconciliationReport.objects.filter(id=report_id).exists()
    report = ReconciliationReport.objects.get(id=report_id)
    assert report.status == ReconciliationStatus.RUNNING

    # Assert chord was invoked with the expected number of checks
    assert 'sigs' in captured
    assert len(captured['sigs']) == 5
