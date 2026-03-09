def test_run_reconciliation_end_to_end(db, monkeypatch):
    """Integration test for run_reconciliation: patch `chord` to synchronously aggregate simulated check results."""
    from apps.reconciliation import tasks
    from apps.reconciliation.models import ReconciliationReport, ReconciliationStatus

    # Simulated check results: one CRITICAL, one LOW
    simulated_checks = [
        {
            'check': 'double_entry',
            'passed': False,
            'issues_count': 1,
            'severity': 'CRITICAL',
            'discrepancies': [{'issue': 'GLOBAL_IMBALANCE'}],
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

    # Patch send_reconciliation_alert to avoid side effects
    class DummyAlert:
        def delay(self, *_args, **_kw):
            return None

    monkeypatch.setattr(tasks, 'send_reconciliation_alert', DummyAlert())

    # Patch chord to synchronously invoke aggregate_results with our simulated checks
    def fake_chord(sigs):
        class Runner:
            def __call__(self, agg_sig):
                # agg_sig is a signature for aggregate_results with report_id as arg
                try:
                    report_id = agg_sig.args[0]
                except Exception:
                    # Fallback if args not present
                    report_id = None
                # Call aggregate_results directly
                tasks.aggregate_results(simulated_checks, report_id)
                return report_id

        return Runner()

    monkeypatch.setattr(tasks, 'chord', fake_chord)

    # Run reconciliation
    report_id = tasks.run_reconciliation(run_type='INTEGRATION_TEST')

    # Verify report updated by aggregate_results
    report = ReconciliationReport.objects.get(id=report_id)
    assert report.status == ReconciliationStatus.CRITICAL
    assert report.total_issues == 1
    assert 'double_entry' in report.checks_summary
