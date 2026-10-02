from monitoring.ops_monitor import format_alert


def test_drift_telegram_alert_explains_scope_samples_and_action():
    alert = {'labels': {'alertname': 'BiometricTenantDataDrift', 'severity': 'warning',
                        'tenant': 'company-a', 'model_version': '12', 'feature': 'face_score'},
             'annotations': {'summary': 'PSI > 0.2', 'description': 'Check data drift'}}
    summary = {'tenants': [{'tenant_id': 'company-a', 'tenant_name': 'Company A',
                            'model_version': '12', 'reference_count': 40, 'current_count': 40,
                            'recommendation': 'investigate_drift'}]}
    message = format_alert(alert, summary)
    assert 'Company A' in message and 'face_score' in message
    assert '40/40' in message and '12' in message
    assert 'xem xét' in message.lower()
