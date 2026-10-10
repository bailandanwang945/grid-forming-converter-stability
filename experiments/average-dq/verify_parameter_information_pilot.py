"""Audit the frozen pilot; export matrices for an independent MATLAB solver."""
from __future__ import annotations

import hashlib
import itertools
import json
from pathlib import Path

import numpy as np

from run_parameter_information_pilot import Family, Evaluator, METHODS, spectral_label

ROOT = Path(__file__).resolve().parents[2]
DEST = ROOT / 'results/parameter-information-pilot'


def main():
    pilot = json.loads((DEST / 'pilot.json').read_text(encoding='utf-8'))
    for name, digest in pilot['provenance'].items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == digest, name
    families = {x: Family(x) for x in (.1, .2, .4)}
    audit = {'cases': [], 'checked_policy_rows': 0,
             'scope': 'diagnostic samples do not establish continuous-family stability'}
    matlab = {'conditions': [], 'points': []}
    for case in pilot['cases']:
        family = families[case['x_pu']]
        bounds = tuple(case['bounds'])
        values = tuple(float(z) for z in np.linspace(bounds[0], bounds[1], 5))
        ev = Evaluator(family, values)
        truth = {point: spectral_label(family.raw(*point))[0]
                 for point in itertools.product(values, repeat=2)}
        for method in METHODS:
            record = case['methods'][method]
            assert len(record['rows']) == 25
            assert len({tuple(r['hidden']) for r in record['rows']}) == 25
            for row in record['rows']:
                assert row['reference'] == truth[tuple(row['hidden'])]
                assert ev.run(method, bounds, tuple(row['hidden'])) == {
                    key: row[key] for key in ('requests', 'order', 'label')}
                audit['checked_policy_rows'] += 1
            assert record['mean_requests'] == np.mean([r['requests'] for r in record['rows']])
        summaries = []
        regions = [('whole-box', bounds)]
        regions.extend((f'axis-{axis}-value-{value}', ev.collapse(bounds, axis, value))
                       for axis in range(2) for value in values)
        for name, region in regions:
            v0, v1, i0, i1 = region
            result = ev.check(region)
            # 101 points per free coordinate; the whole box retains 5x5 samples.
            samples = [values, values] if name == 'whole-box' else [
                (v0,) if v0 == v1 else np.linspace(v0, v1, 101),
                (i0,) if i0 == i1 else np.linspace(i0, i1, 101)]
            labels = [spectral_label(family.raw(v, i))[0]
                      for v, i in itertools.product(*samples)]
            counts = {label: labels.count(label) for label in set(labels)}
            summaries.append({'name': name, 'bounds': region, 'condition': result,
                              'sample_labels': counts})
            matlab['conditions'].append({'case_x': family.x, 'name': name,
                'bounds': region, 'expected': result['label'],
                'center': family.raw((v0+v1)/2, (i0+i1)/2).tolist(),
                'vertices': [family.raw(v, i).tolist()
                             for v, i in itertools.product((v0, v1), (i0, i1))]})
        for point, label in truth.items():
            matlab['points'].append({'case_x': family.x, 'parameters': point,
                'expected': label, 'matrix': family.raw(*point).tolist()})
        audit['cases'].append({'x_pu': family.x, 'bounds': bounds, 'regions': summaries})
        homogeneous = sum(len(s['sample_labels']) == 1 for s in summaries[1:])
        print(f"X={family.x}, box={bounds[:2]}: homogeneous sampled slices {homogeneous}/10; "
              f"common-P classified {sum(s['condition']['label'] != 'pending' for s in summaries[1:])}/10",
              flush=True)
    assert audit['checked_policy_rows'] == 1200
    for name, payload in [('audit.json', audit), ('matlab-input.json', matlab)]:
        (DEST / name).write_text(json.dumps(payload, indent=2, allow_nan=False)+'\n', encoding='utf-8')
    if (DEST / 'lmi-diagnostic.json').exists():
        lmi = json.loads((DEST / 'lmi-diagnostic.json').read_text(encoding='utf-8'))
        checked = []
        for record in lmi['records']:
            sample = next(s for s in matlab['conditions'] if s['case_x'] == .4
                          and s['name'] == record['name']
                          and np.array_equal(s['bounds'], record['bounds']))
            p = np.array(record['p'])
            minimum_p = float(np.linalg.eigvalsh(p).min())
            margin = min(-float(np.linalg.eigvalsh(np.array(a).T@p+p@np.array(a)).max())
                         for a in sample['vertices'])
            stable = bool(np.isfinite(p).all() and minimum_p > 1e-8 and margin > 1e-6)
            assert stable == record['stable_sufficient_condition']
            assert np.isclose(minimum_p, record['p_min_eigenvalue'], rtol=1e-6, atol=1e-10)
            assert np.isclose(margin, record['minimum_q_margin'], rtol=1e-6, atol=1e-10)
            checked.append({'name': record['name'], 'p_minimum': minimum_p,
                            'q_margin': margin, 'stable': stable})
        (DEST / 'lmi-python-readback.json').write_text(
            json.dumps({'checked': checked}, indent=2, allow_nan=False)+'\n', encoding='utf-8')
        print('LMI_PYTHON_READBACK_OK', flush=True)
    print('V1_AUDIT_OK', flush=True)


if __name__ == '__main__':
    main()
