import numpy as np
from app.template_lifecycle import TemplateConfig, evaluate_template


def samples():
    rows = []
    for i in range(70):
        genuine = i < 40
        rows.append({'id': str(i), 'embedding': [1., .1] if genuine else [0., 1.],
                     'truth': genuine, 'random_audit': True, 'integrity_passed': genuine,
                     'quality': {'quality': .95}, 'score': .95 if genuine else .1,
                     'threshold': .7, 'media_sha256': str(i), 'encoder': 'same'})
    return rows


def test_trusted_template_candidate_preserves_security_on_disjoint_holdout():
    result = evaluate_template([[1., 0.]], samples(), .7, TemplateConfig())
    assert result['status'] == 'APPROVED'
    assert set(result['training_ids']).isdisjoint(result['evaluation_ids'])
    assert np.linalg.norm(result['embeddings'][-1]) > .99


def test_predictions_alone_or_duplicate_captures_cannot_update_templates():
    rows = samples()
    for row in rows:
        row['truth'] = None
    assert evaluate_template([[1., 0.]], rows, .7, TemplateConfig())['status'] == 'PENDING_REVIEW'
    rows = samples()
    for row in rows:
        row['media_sha256'] = 'replay'
    assert evaluate_template([[1., 0.]], rows, .7, TemplateConfig())['status'] == 'PENDING_REVIEW'


def test_identity_conflicts_and_mixed_encoders_block_template_changes():
    rows = samples()
    rows[1]['encoder'] = 'different'
    assert evaluate_template([[1., 0.]], rows, .7, TemplateConfig())['status'] == 'PENDING_REVIEW'


def test_template_activation_and_rollback_preserve_original_enrollment():
    from app.db import Base
    from app.models import ActiveTemplate, BiometricSample, Person
    from app.observation import templates
    from app.template_lifecycle import rollback_template, update_template
    from sqlalchemy import create_engine, select
    from sqlalchemy.orm import Session

    engine = create_engine('sqlite://')
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as db:
        person = Person(id='employee', external_id='employee', display_name='Fixture', tenant_id='demo')
        db.add(person)
        db.add(BiometricSample(person_id='employee', modality='face', embedding=[1., 0.], quality=.9, sha256='old'))
        db.commit()
        original, version, _ = templates(db, person, 'face')
        rows = [{**r, 'template_version': version} for r in samples()]
        activated = update_template(db, person.id, 'face', rows, .7, TemplateConfig())
        db.commit()
        assert activated['status'] == 'ACTIVE'
        assert len(templates(db, person, 'face')[0]) == 2
        assert update_template(db, person.id, 'face', rows, .7, TemplateConfig())['status'] == 'PENDING_REVIEW'
        assert rollback_template(db, person.id, 'face')['status'] == 'ROLLED_BACK'
        db.commit()
        assert templates(db, person, 'face')[0] == original
        assert len(list(db.scalars(select(BiometricSample)))) == 1
        assert db.get(ActiveTemplate, (person.id, 'voice')) is None
        from app.template_lifecycle import append_enrollment
        append_enrollment(db, person.id, 'face', [0.9, 0.1], 'same')
        db.commit()
        assert len(templates(db, person, 'face')[0]) == 2
        rollback_template(db, person.id, 'face')
        db.commit()
        assert templates(db, person, 'face')[0] == original
    engine.dispose()
    rows = samples()
    rows[-1]['media_sha256'] = rows[0]['media_sha256']
    assert evaluate_template([[1., 0.]], rows, .7, TemplateConfig())['status'] == 'PENDING_REVIEW'
