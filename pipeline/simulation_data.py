"""Reproducible unit vectors and synthetic truth, never production biometric data."""
import numpy as np

DIMENSIONS = 201
BASELINE_THRESHOLD = .8


def window(prefix, seed, drift=True, count=100, security_failure=False):
    rng = np.random.default_rng(seed)
    jitters = rng.permutation(np.linspace(-.01, .01, 50))
    rows = []
    for index in range(count):
        person = index % 50
        truth = (index // 50) % 2 == 0
        score = (.60 if drift else .90) + jitters[person] if truth else (.35 if drift else .1)
        if security_failure and not truth:
            score = .65
        vector, template = np.zeros(DIMENSIONS), np.zeros(DIMENSIONS)
        template[person + 1] = 1.
        vector[0], vector[person + 1] = (.6 if drift else .1), score
        vector[51 + person] = np.sqrt(1 - float(vector @ vector))
        rows.append({'id': f'{prefix}-{index}', 'person_id': f'synthetic-{person:03}',
            'encoder': 'synthetic-unit-vectors-v1', 'embedding': vector.tolist(),
            'template': template.tolist(), 'score': float(vector @ template),
            'threshold': BASELINE_THRESHOLD, 'quality': {'quality': .9},
            'template_age_days': 10 if person < 25 else 120,
            'truth': truth, 'random_audit': True, 'source': 'synthetic'})
    return rows


def dataset(seed):
    rng = np.random.default_rng(seed)
    rows = []
    for person in range(50):
        for capture in range(3):
            vector = np.zeros(DIMENSIONS)
            vector[0] = np.sqrt(.4)
            vector[person + 1] = np.sqrt(.22 + rng.uniform(-.01, .01))
            vector[51 + person * 3 + capture] = np.sqrt(1 - float(vector @ vector))
            rows.append({'person_id': f'train-{person:03}', 'embedding': vector.tolist(),
                         'source': 'synthetic'})
    return rows
