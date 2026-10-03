"""Reversible templates built only from reviewed, distinct trusted captures."""
import math
from dataclasses import dataclass

import numpy as np
from sqlalchemy import select

from .biometrics import cosine, normalize
from .models import ActiveTemplate, Person, TemplateVersion
from .observation import templates


@dataclass(frozen=True)
class TemplateConfig:
    min_observations: int = 10
    min_holdout_per_class: int = 20
    min_quality: float = .7
    min_margin: float = .1
    min_consistency: float = .85
    max_fmr: float = .01
    max_templates: int = 8

    def __post_init__(self):
        if (self.min_observations < 2 or self.min_holdout_per_class < 1 or self.max_templates < 2
                or any(not math.isfinite(v) or not 0 <= v <= 1 for v in
                       (self.min_quality, self.min_margin, self.min_consistency, self.max_fmr))):
            raise ValueError('Invalid template safety limits')


def evaluate_template(old, rows, threshold, config):
    pending = {'status': 'PENDING_REVIEW', 'reason': 'insufficient independent trusted evidence'}
    available = [r for r in rows if r.get('embedding') is not None and type(r.get('truth')) is bool
                 and r.get('random_audit')]
    if len({r['encoder'] for r in available}) != 1:
        return pending
    labels = {}
    for row in available:
        digest = row['media_sha256']
        if digest in labels and labels[digest] != row['truth']:
            return {**pending, 'reason': 'identity conflict for the same capture'}
        labels[digest] = row['truth']
    trusted, seen = [], set()
    for row in available:
        if (row['truth'] and row.get('integrity_passed') and row['quality']['quality'] >= config.min_quality
                and row['score'] - row['threshold'] >= config.min_margin and row['media_sha256'] not in seen):
            trusted.append(row)
            seen.add(row['media_sha256'])
    if len(trusted) < config.min_observations + config.min_holdout_per_class or len(old) >= config.max_templates:
        return pending
    training = trusted[:config.min_observations]
    centroid = normalize(np.mean([normalize(np.asarray(r['embedding'])) for r in training], axis=0))
    if min(cosine(r['embedding'], centroid) for r in training) < config.min_consistency:
        return {**pending, 'reason': 'inconsistent trusted observations'}
    train_hashes = {r['media_sha256'] for r in training}
    evaluation, eval_hashes = [], set()
    for row in available:
        if row['media_sha256'] not in train_hashes | eval_hashes:
            evaluation.append(row)
            eval_hashes.add(row['media_sha256'])
    genuine, impostor = [r for r in evaluation if r['truth']], [r for r in evaluation if not r['truth']]
    if min(len(genuine), len(impostor)) < config.min_holdout_per_class:
        return pending
    candidate = [*old, centroid.tolist()]

    def metrics(vectors):
        return {'fmr': float(np.mean([max(cosine(r['embedding'], v) for v in vectors) >= threshold for r in impostor])),
                'fnmr': float(np.mean([max(cosine(r['embedding'], v) for v in vectors) < threshold for r in genuine]))}

    before, after = metrics(old), metrics(candidate)
    passed = after['fmr'] <= min(before['fmr'], config.max_fmr) and after['fnmr'] <= before['fnmr']
    return {'status': 'APPROVED' if passed else 'REJECTED', 'old': before, 'candidate': after,
            'embeddings': candidate, 'training_ids': [r['id'] for r in training],
            'evaluation_ids': [r['id'] for r in evaluation], 'encoder': available[0]['encoder']}


def update_template(db, person_id, modality, rows, threshold, config):
    person = db.scalar(select(Person).where(Person.id == person_id).with_for_update())
    if person is None:
        raise ValueError('Unknown employee')
    old, previous_id, created = templates(db, person, modality)
    rows = [r for r in rows if r.get('template_version') == previous_id]
    result = evaluate_template(old, rows, threshold, config)
    if result['status'] != 'APPROVED':
        return {**{k: v for k, v in result.items() if k != 'embeddings'},
                'person_id': person_id, 'modality': modality}
    pointer = db.get(ActiveTemplate, (person_id, modality))
    if pointer is None:
        baseline = TemplateVersion(tenant_id=person.tenant_id, person_id=person_id, modality=modality,
                                    encoder=result['encoder'], embeddings=old, state='PREVIOUS', created_at=created)
        db.add(baseline)
        db.flush()
        previous_id = baseline.id
    version = TemplateVersion(tenant_id=person.tenant_id, person_id=person_id, modality=modality,
                               encoder=result['encoder'], embeddings=result['embeddings'],
                               previous_id=previous_id, state='ACTIVE',
                               evidence={k: v for k, v in result.items() if k != 'embeddings'})
    db.add(version)
    db.flush()
    if pointer is None:
        db.add(ActiveTemplate(person_id=person_id, modality=modality, version_id=version.id))
    else:
        db.get(TemplateVersion, pointer.version_id).state = 'PREVIOUS'
        pointer.version_id = version.id
    return {'status': 'ACTIVE', 'version': version.id, 'previous_version': previous_id}


def append_enrollment(db, person_id, modality, embedding, encoder):
    """Authorized enrollment must also update an already active versioned template."""
    db.scalar(select(Person).where(Person.id == person_id).with_for_update())
    pointer = db.get(ActiveTemplate, (person_id, modality))
    if pointer is None:
        return
    previous = db.get(TemplateVersion, pointer.version_id)
    if previous.encoder != encoder:
        raise ValueError('Enrollment encoder is incompatible with the active template')
    version = TemplateVersion(tenant_id=previous.tenant_id, person_id=person_id, modality=modality,
        encoder=encoder, embeddings=[*previous.embeddings, embedding], previous_id=previous.id,
        state='ACTIVE', evidence={'source': 'authorized_enrollment'})
    db.add(version)
    db.flush()
    previous.state, pointer.version_id = 'PREVIOUS', version.id


def rollback_template(db, person_id, modality):
    db.scalar(select(Person).where(Person.id == person_id).with_for_update())
    pointer = db.get(ActiveTemplate, (person_id, modality))
    current = db.get(TemplateVersion, pointer.version_id) if pointer else None
    if current is None or not current.previous_id:
        raise ValueError('No previous template')
    previous = db.get(TemplateVersion, current.previous_id)
    current.state, previous.state = 'ROLLED_BACK', 'ACTIVE'
    pointer.version_id = previous.id
    return {'status': 'ROLLED_BACK', 'version': previous.id}
