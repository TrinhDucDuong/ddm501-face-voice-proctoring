import json
from types import SimpleNamespace

import numpy as np
import pytest
from app.explainability import explain
from sqlalchemy import create_engine, text

from monitoring import ops_monitor
from monitoring.drift_monitor import load_feedback
from pipeline.build_dashboard import build
from pipeline.evaluation import (
    identity_evaluation,
    policy_scores,
    select_trial,
    threshold_trials,
)
from pipeline.promotion_gate import promote
from pipeline.responsible_ai_report import build_report


def test_identity_holdout_has_no_subject_overlap_and_matches_serving():
    rows = []
    for subject in range(20):
        vector = np.eye(20)[subject]
        for sample in range(3):
            rows.append({'person_id':str(subject), 'embedding':(vector + .001*sample).tolist()})
    threshold, metrics, report = identity_evaluation(rows)
    assert metrics['holdout_far'] == metrics['holdout_frr'] == 0
    assert threshold > 0
    for fold in report['folds']:
        assert not set(fold['train_identities']) & set(fold['test_identities'])
        assert not set(report['holdout_identities']) & (set(fold['train_identities']) | set(fold['test_identities']))
    assert metrics['cv_folds'] == 4
    assert report['selection_method'] == 'minimum_margin_meeting_internal_cv_budget'
    changed = json.loads(json.dumps(rows))
    for row in changed:
        if row['person_id'] in report['holdout_identities']:
            row['embedding'] = [1.] * 20
    other_threshold, other_metrics, _ = identity_evaluation(changed)
    assert other_threshold == threshold
    assert other_metrics['cv_far'] == metrics['cv_far']
    assert other_metrics['holdout_far'] == 1
    positive, negative = policy_scores(rows)
    assert len(positive) == 60 and len(negative) == 190
    assert positive.min() > .99 and negative.max() < .01
    with pytest.raises(ValueError):
        identity_evaluation(rows[:3])
    with pytest.raises(ValueError):
        threshold_trials(positive[:2], negative)
    trials = threshold_trials(positive, negative)
    assert select_trial(trials, 'far_constrained')['far'] <= .05
    assert select_trial(trials, 'balanced_error')['frr'] == 0
    with pytest.raises(ValueError):
        select_trial(trials, 'unknown')


def test_unsafe_cli_promotion_preserves_champion(monkeypatch):
    calls = []
    candidate = SimpleNamespace(run_id='new', version='9')
    client = SimpleNamespace(get_run=lambda _:SimpleNamespace(data=SimpleNamespace(metrics={})),
                             set_model_version_tag=lambda *args:calls.append(('tag',args)),
                             set_registered_model_alias=lambda *args:calls.append(('alias',args)))
    with pytest.raises(RuntimeError, match='rejected'):
        promote(client, 'bundle', candidate)
    assert all(c[0] != 'alias' for c in calls)
    with pytest.raises(RuntimeError, match='another'):
        promote(client, 'bundle', candidate, 'different-run')


def test_policy_explanation_keeps_other_modality_and_quality_constraints():
    result = explain({'face':.3,'voice':.2}, {'face':.1,'voice':.9}, {'face':.5,'voice':.4})
    assert result['score_margins']['face'] == -.2
    counterfactual = result['counterfactuals']['face']
    assert not counterfactual['accepted_after_score_change']
    assert set(counterfactual['remaining_reasons']) == {'low_face_quality','voice_mismatch'}
    assert not any(r['accepted'] for r in result['sensitivity'])
    assert explain({'face':None,'voice':.9},{}, {'face':.5,'voice':.4})['counterfactuals']['face']['status'] == 'requires_capture'


def test_synthetic_labels_do_not_enter_human_performance(tmp_path):
    url = f"sqlite:///{(tmp_path/'labels.db').as_posix()}"
    engine = create_engine(url)
    with engine.begin() as db:
        db.execute(text('CREATE TABLE verification_events (id TEXT,created_at INTEGER,accepted BOOLEAN)'))
        db.execute(text('CREATE TABLE verification_feedback (event_id TEXT,is_genuine BOOLEAN,reviewer TEXT)'))
        db.execute(text("INSERT INTO verification_events VALUES ('a',1,1),('b',2,0),('c',3,1)"))
        db.execute(text("INSERT INTO verification_feedback VALUES "
                        "('a',1,'operator:proctor'),('b',0,'synthetic-simulation'),('c',1,'untrusted-client')"))
    assert len(load_feedback(url,20,'human')) == 1
    assert load_feedback(url,20,'human').created_at.tolist() == [1]
    assert load_feedback(url,20,'synthetic').created_at.tolist() == [2]
    with pytest.raises(ValueError):
        load_feedback(url,20,'all')
    engine.dispose()


def test_fairness_requires_both_classes_and_reports_uncertainty():
    rows = [{'label_source':'human','quality_slice':s,'reviewed':20,'genuine_count':10,'impostor_count':10,
             'accuracy':.9,'false_accept_rate':0,'false_reject_rate':.2} for s in ['low','high']]
    result = build_report(rows)
    assert result['gate'] == 'pass'
    assert result['slices'][0]['false_accept_rate_ci95'][1] > 0
    rows[0]['impostor_count'] = 0
    assert build_report(rows)['gate'] == 'insufficient_data'


def test_grafana_overview_has_correct_sources_and_layout():
    dashboard = build()
    assert dashboard['uid'] == 'biometric-overview'
    assert len(dashboard['panels']) == 10
    assert [v['name'] for v in dashboard['templating']['list']] == ['project']
    assert all(p['datasource']['uid'] == 'prometheus' for p in dashboard['panels'])
    traffic = next(p for p in dashboard['panels'] if p['title'] == 'API traffic')
    assert 'biometric_requests_total' in traffic['targets'][0]['expr']
    assert '/v1/simulation.*' in traffic['targets'][0]['expr']
    assert 'biometric_verifications_total' not in traffic['targets'][0]['expr']
    quality = next(p for p in dashboard['panels'] if p['title'].startswith('Human-reviewed quality'))
    assert all('source="human"' in t['expr'] for t in quality['targets'])
    assert 'biometric_reviewed_report_success' in quality['targets'][0]['expr']
    assert len({p['id'] for p in dashboard['panels']}) == len(dashboard['panels'])
    for i, first in enumerate(dashboard['panels']):
        a = first['gridPos']
        assert 0 <= a['x'] < a['x'] + a['w'] <= 24 and a['h'] > 0
        for second in dashboard['panels'][i+1:]:
            b = second['gridPos']
            assert not (a['x'] < b['x']+b['w'] and b['x'] < a['x']+a['w'] and a['y'] < b['y']+b['h'] and b['y'] < a['y']+a['h'])


def test_telegram_does_not_expose_token_on_error(monkeypatch, caplog):
    monkeypatch.setenv('TELEGRAM_BOT_TOKEN','sensitive-token')
    monkeypatch.setenv('TELEGRAM_CHAT_ID','123')
    def fail(*args,**kwargs):
        raise RuntimeError('transport unavailable')
    monkeypatch.setattr(ops_monitor,'request_telegram',fail)
    assert not ops_monitor.send_telegram({'status':'firing','alerts':[]})
    assert 'sensitive-token' not in caplog.text
    monkeypatch.setattr(ops_monitor,'request_telegram',lambda *a,**k:(200,{'ok':True}))
    assert ops_monitor.send_telegram({'status':'resolved','alerts':[]})
    monkeypatch.delenv('TELEGRAM_BOT_TOKEN')
    assert not ops_monitor.send_telegram({'alerts':[]})


def test_reports_escape_html(monkeypatch,tmp_path):
    monkeypatch.setattr(ops_monitor,'REPORT_DIR',tmp_path)
    ops_monitor.write_report('test',{'value':'<script>alert(1)</script>'})
    assert '<script>' not in (tmp_path/'test.html').read_text()
    assert json.loads((tmp_path/'test.json').read_text())['value'].startswith('<script>')
