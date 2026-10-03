"""Identity-disjoint evaluation matching serving's maximum-template comparison."""
import itertools

import numpy as np


def policy_scores(rows, max_impostor_pairs=10000, max_templates=20):
    subjects = {}
    for row in rows:
        vector = np.asarray(row['embedding'], dtype=float)
        subjects.setdefault(str(row['person_id']), []).append(vector / np.linalg.norm(vector))
    genuine, impostor = [], []
    for person, vectors in subjects.items():
        if len(vectors) > max_templates:
            subjects[person] = [vectors[i] for i in np.linspace(0, len(vectors) - 1, max_templates, dtype=int)]
    for vectors in subjects.values():
        for index, probe in enumerate(vectors):
            references = vectors[:index] + vectors[index + 1:]
            if references:
                genuine.append(max(float(probe @ ref) for ref in references))
    people = sorted(subjects)
    if len(people) * (len(people) - 1) // 2 <= max_impostor_pairs:
        comparisons = itertools.combinations(people, 2)
    else:
        rng, selected = np.random.default_rng(501), set()
        while len(selected) < max_impostor_pairs:
            a, b = sorted(rng.choice(len(people), size=2, replace=False).tolist())
            selected.add((a, b))
        comparisons = ((people[a], people[b]) for a, b in sorted(selected))
    for first, second in comparisons:
        impostor.append(max(float(subjects[first][0] @ ref) for ref in subjects[second]))
    return np.asarray(genuine), np.asarray(impostor)


def threshold_trials(positive, negative):
    if min(len(positive), len(negative)) < 5:
        raise ValueError('At least five genuine and impostor comparisons required')
    grid = np.linspace(-0.2, 0.95, 1151)
    return [{'threshold': float(t), 'far': float(np.mean(negative >= t)),
             'frr': float(np.mean(positive < t))} for t in grid]


def select_trial(trials, objective='minimax'):
    if objective == 'minimax':
        return min(trials, key=lambda t: (max(t['far'], t['frr']), t['far'] + t['frr']))
    if objective == 'balanced_error':
        return min(trials, key=lambda t: (t['far'] + t['frr'], max(t['far'], t['frr'])))
    if objective == 'far_constrained':
        return min(trials, key=lambda t: (t['far'] > .05, t['frr'] if t['far'] <= .05 else t['far'], t['far']))
    raise ValueError('Unknown objective')


def identity_evaluation(rows, folds=5, max_error_rate=.20):
    if folds < 3 or not 0 <= max_error_rate <= 1:
        raise ValueError('At least three partitions and a valid error budget required')
    people = sorted({str(row['person_id']) for row in rows})
    if len(people) < 10:
        raise ValueError('Identity-disjoint evaluation requires at least ten identities')
    partitions = np.array_split(np.random.default_rng(501).permutation(people), folds)
    holdout_ids = set(partitions[0])
    calibration = [r for r in rows if str(r['person_id']) not in holdout_ids]
    results = []
    validation_scores = []
    for index, held_out in enumerate(partitions[1:], start=1):
        held_out = set(held_out)
        train = [r for r in calibration if str(r['person_id']) not in held_out]
        test = [r for r in calibration if str(r['person_id']) in held_out]
        positive, negative = policy_scores(train)
        trials = threshold_trials(positive, negative)
        best = select_trial(trials)
        test_positive, test_negative = policy_scores(test)
        if min(len(test_positive), len(test_negative)) < 5:
            raise ValueError('Insufficient held-out identity comparisons')
        validation_scores.append((best['threshold'],test_positive,test_negative))
        results.append({'fold': index, 'train_identities': sorted({str(r['person_id']) for r in train}),
                        'test_identities': sorted(held_out), 'threshold': best['threshold'],
                        'far': float(np.mean(test_negative >= best['threshold'])),
                        'frr': float(np.mean(test_positive < best['threshold'])),
                        'positive_pairs': len(test_positive), 'negative_pairs': len(test_negative)})
    # Select the smallest conservative adjustment meeting the declared CV budget.
    # Holdout identities never enter any fold's training or margin selection.
    margin_trials = []
    for margin in (0., .002, .005, .01, .02):
        far = float(np.mean([np.mean(n >= t+margin) for t,p,n in validation_scores]))
        frr = float(np.mean([np.mean(p < t+margin) for t,p,n in validation_scores]))
        margin_trials.append({'margin':margin,'cv_far':far,'cv_frr':frr,
                              'passed':max(far,frr) <= max_error_rate})
    selection = next((t for t in margin_trials if t['passed']),margin_trials[0])
    margin = selection['margin']
    for result, (threshold, p, n) in zip(results,validation_scores,strict=True):
        result.update(threshold=threshold+margin,far=float(np.mean(n >= threshold+margin)),
                      frr=float(np.mean(p < threshold+margin)))
    positive, negative = policy_scores(calibration)
    trials = threshold_trials(positive, negative)
    best = select_trial(trials)
    threshold = best['threshold'] + margin
    holdout_positive, holdout_negative = policy_scores([r for r in rows if str(r['person_id']) in holdout_ids])
    if min(len(holdout_positive),len(holdout_negative)) < 5:
        raise ValueError('Insufficient registration holdout comparisons')
    metrics = {'far':float(np.mean(negative >= threshold)), 'frr':float(np.mean(positive < threshold)),
               'positive_pairs': len(positive), 'negative_pairs': len(negative),
               'cv_far':selection['cv_far'],'cv_frr':selection['cv_frr'],
               'holdout_far':float(np.mean(holdout_negative >= threshold)),
               'holdout_frr':float(np.mean(holdout_positive < threshold)),
               'holdout_positive_pairs':len(holdout_positive),'holdout_negative_pairs':len(holdout_negative),
               'cv_folds':folds-1,'safety_margin':margin}
    return threshold, metrics, {'method':'identity-disjoint-max-template',
                                'registration_holdout_fold':0,'holdout_identities':sorted(holdout_ids),
                                'selection_method':'minimum_margin_meeting_internal_cv_budget',
                                'max_error_rate':max_error_rate,'margin_trials':margin_trials,
                                'folds':results,'trials':trials}
