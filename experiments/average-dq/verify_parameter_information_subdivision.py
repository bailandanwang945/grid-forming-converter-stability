"""Post-pilot diagnostic: do not confuse a failed common-P search with necessity."""
import json
from pathlib import Path

import numpy as np

from run_parameter_information_pilot import Family, inertia_check

ROOT = Path(__file__).resolve().parents[2]


def main():
    family = Family(.4)
    records = []
    # Chosen after the initial experiment as a diagnostic, not a held-out trial.
    for fixed_axis, segments in ((1, 256), (0, 512)):
        cuts = np.linspace(1., 3., segments+1)
        results = []
        for lo, hi in zip(cuts[:-1], cuts[1:]):
            def matrix(z):
                return family.raw(z, 3.) if fixed_axis == 1 else family.raw(3., z)
            results.append(inertia_check([matrix(lo), matrix(hi)], matrix((lo+hi)/2)))
        assert all(r['label'] == 'stable' for r in results)
        records.append({'fixed_axis': 'current-pi' if fixed_axis == 1 else 'voltage-pi',
            'fixed_value': 3., 'remaining_interval': [1., 3.], 'segments': segments,
            'stable_segments': len(results), 'minimum_margin': min(r['margin'] for r in results),
            'maximum_residual': max(r['residual'] for r in results)})
    destination = ROOT/'results/parameter-information-pilot/subdivision-diagnostic.json'
    destination.write_text(json.dumps({'x_pu': .4, 'scope':
        'Post-hoc floating-point sufficient-condition coverage of two continuous slices; '
        'not interval arithmetic, not a fair re-evaluation of the eight policies',
        'slices': records}, indent=2, allow_nan=False)+'\n', encoding='utf-8')
    print(json.dumps(records), flush=True)
    print('V1_SUBDIVISION_DIAGNOSTIC_OK', flush=True)


if __name__ == '__main__':
    main()
