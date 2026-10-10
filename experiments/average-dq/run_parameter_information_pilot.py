"""Bounded V1 inquiry pilot. Known algorithms, synthetic exact disclosures only."""
from __future__ import annotations

import hashlib
import itertools
import json
import platform
import sys
import time
import warnings
from collections import Counter
from functools import lru_cache
from pathlib import Path

import numpy as np
import scipy
from scipy.linalg import solve_continuous_lyapunov

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from backend.core.average_dq_model import build_average_dq_model
from backend.core.average_dq_presets import build_average_dq_ablation_anchor_case

START = time.perf_counter()
METRIC_TOL = 1e-5
METHODS = ('all-information', 'fixed-v', 'fixed-i', 'sensitivity',
           'label-entropy', 'ec2', 'slice-lookahead', 'exact-dp')


def deadline():
    if time.perf_counter() - START > 115:
        raise TimeoutError('V1 pilot reached 115-second deadline')


def spectral_label(a):
    alpha = float(np.max(np.linalg.eigvals(a).real))
    return ('stable' if alpha < -METRIC_TOL else
            'unstable' if alpha > METRIC_TOL else 'pending'), alpha


def inertia_check(matrices, center):
    """Numerical common-P condition for the declared convex matrix family."""
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error')
            p = solve_continuous_lyapunov(center.T, -np.eye(len(center)))
        p = (p + p.T) / 2
        q_center = center.T @ p + p @ center
        residual = float(np.linalg.norm(q_center + np.eye(len(center)), 2))
        scale = max(1.0, float(np.linalg.norm(center, 2) * np.linalg.norm(p, 2)))
        eig_p = np.linalg.eigvalsh(p)
        gap = float(np.min(np.abs(eig_p)))
        p_scale = max(1.0, float(np.linalg.norm(p, 2)))
        margins = [-float(np.linalg.eigvalsh(a.T @ p + p @ a)[-1])
                   for a in matrices]
        margin = min(margins)
        if (not np.all(np.isfinite(p)) or residual > 1e-8 * scale or
                gap <= 1e-10 * p_scale or margin <= 1e-8 * scale):
            return dict(label='pending', residual=residual, margin=margin,
                        inertia_gap=gap, negative_inertia=None)
        negative = int(np.count_nonzero(eig_p < 0))
        return dict(label='unstable' if negative else 'stable', residual=residual,
                    margin=margin, inertia_gap=gap, negative_inertia=negative)
    except (ValueError, np.linalg.LinAlgError, Warning):
        return dict(label='pending', residual=None, margin=None,
                    inertia_gap=None, negative_inertia=None)


class Family:
    def __init__(self, x):
        self.x = x
        self.vertices = {}
        self.source_points = []
        for v, i in itertools.product((0.5, 3.0), repeat=2):
            model = self.build(v, i, 1e-5)
            self.vertices[v, i] = model.linearization.closed_state_matrix
            self.source_points.append(model.operating_point.state)
        assert max(np.linalg.norm(s-self.source_points[0], np.inf)
                   for s in self.source_points) < 1e-10
        self.validation = []
        for v, i in ((1.375, 2.125), (2.25, 0.875)):
            direct = self.build(v, i, 1e-5)
            second = self.build(v, i, 5e-6)
            predicted = self.raw(v, i)
            error = np.linalg.norm(predicted-direct.linearization.closed_state_matrix) / max(
                1., np.linalg.norm(predicted))
            step_error = np.linalg.norm(predicted-second.linearization.closed_state_matrix) / max(
                1., np.linalg.norm(predicted))
            assert max(error, step_error) < 2e-7
            self.validation.append(dict(v=v, i=i, interpolation_relative=float(error),
                                        second_step_relative=float(step_error)))

    def build(self, v, i, step):
        deadline()
        topology, parameters = build_average_dq_ablation_anchor_case()
        topology.lines[0].reactance_pu = self.x
        parameters.voltage_proportional_gain_pu *= v
        parameters.voltage_integral_gain_per_s *= v
        parameters.current_proportional_gain_pu *= i
        parameters.current_integral_gain_per_s *= i
        return build_average_dq_model(topology, parameters, relative_step=step)

    def raw(self, v, i):
        tv, ti = (v-.5)/2.5, (i-.5)/2.5
        return sum(weight*a for weight, a in (
            ((1-tv)*(1-ti), self.vertices[.5, .5]),
            ((1-tv)*ti, self.vertices[.5, 3.]),
            (tv*(1-ti), self.vertices[3., .5]), (tv*ti, self.vertices[3., 3.])))


class Evaluator:
    def __init__(self, family, values):
        self.family, self.values = family, values
        self.counts = Counter()

    def matrix(self, v, i):
        self.counts['matrix'] += 1
        return self.family.raw(v, i)

    def alpha(self, v, i):
        self.counts['eig'] += 1
        return spectral_label(self.matrix(v, i))

    @lru_cache(maxsize=None)
    def check(self, bounds):
        deadline()
        self.counts['box_check'] += 1
        v0, v1, i0, i1 = bounds
        if v0 == v1 and i0 == i1:
            label, _ = self.alpha(v0, i0)
            return dict(label=label, method='point-spectrum')
        matrices = [self.matrix(v, i) for v, i in itertools.product((v0,v1),(i0,i1))]
        self.counts['lyapunov'] += 1
        result = inertia_check(matrices, self.matrix((v0+v1)/2, (i0+i1)/2))
        result['method'] = 'common-inertia-numerical-condition'
        return result

    @staticmethod
    def collapse(bounds, axis, value):
        b = list(bounds)
        b[2*axis:2*axis+2] = (value,value)
        return tuple(b)

    def candidates(self, bounds):
        return [j for j in range(2) if bounds[2*j] != bounds[2*j+1]]

    def sensitivity(self, bounds, axis):
        mid = [(bounds[0]+bounds[1])/2, (bounds[2]+bounds[3])/2]
        width = bounds[2*axis+1] - bounds[2*axis]
        step = 1e-4 * width
        plus, minus = mid.copy(), mid.copy()
        plus[axis] += step
        minus[axis] -= step
        return abs(self.alpha(*plus)[1]-self.alpha(*minus)[1])/(2*step)*width

    def grid(self, bounds):
        points = list(itertools.product(*[
            self.values if bounds[2*j] != bounds[2*j+1] else (bounds[2*j],)
            for j in range(2)]))
        return [(point, self.alpha(*point)[0]) for point in points]

    @staticmethod
    def entropy(labels):
        n = len(labels)
        return -sum((c/n)*np.log2(c/n) for c in Counter(labels).values())

    def score(self, method, bounds, axis, grid=None):
        if method == 'sensitivity':
            return self.sensitivity(bounds, axis)
        if method in ('slice-lookahead','exact-dp'):
            costs = [self.optimal(self.collapse(bounds,axis,z))[0]
                     if method == 'exact-dp' else
                     float(self.check(self.collapse(bounds,axis,z))['label'] == 'pending')
                     for z in self.values]
            return -float(np.mean(costs))
        assert grid is not None
        labels = [label for _,label in grid]
        n = len(grid)
        groups = [[label for point,label in grid if point[axis] == z] for z in self.values]
        if method == 'label-entropy':
            return self.entropy(labels)-sum(len(g)/n*self.entropy(g) for g in groups if g)
        masses = [count/n for count in Counter(labels).values()]
        remaining = 0.
        for g in groups:
            local = [count/n for count in Counter(g).values()]
            remaining += len(g)/n * sum(a*b for a,b in itertools.combinations(local,2))
        return sum(a*b for a,b in itertools.combinations(masses,2))-remaining

    @lru_cache(maxsize=None)
    def optimal(self, bounds):
        if self.check(bounds)['label'] != 'pending':
            return 0., None
        choices = self.candidates(bounds)
        if not choices:
            return 0., None
        costs = [(1+np.mean([self.optimal(self.collapse(bounds,j,z))[0]
                            for z in self.values]),j) for j in choices]
        cost,j = min(costs)
        return float(cost),j

    def run(self, method, bounds, hidden):
        requested = []
        while True:
            result = self.check(bounds)
            choices = self.candidates(bounds)
            if not choices or (method != 'all-information' and result['label'] != 'pending'):
                return dict(requests=len(requested), order=requested, label=result['label'])
            if method in ('all-information','fixed-v','fixed-i'):
                order = (1,0) if method == 'fixed-i' else (0,1)
                axis = next(j for j in order if j in choices)
            elif method == 'exact-dp':
                axis = self.optimal(bounds)[1]
            else:
                grid = self.grid(bounds) if method in ('label-entropy','ec2') else None
                scores = {j:self.score(method,bounds,j,grid) for j in choices}
                axis = min(choices, key=lambda j:(-scores[j],j))
            assert axis is not None
            requested.append('voltage-pi' if axis == 0 else 'current-pi')
            bounds = self.collapse(bounds,axis,hidden[axis])


def main():
    # Regression against the forbidden corner-and-center shortcut.
    bad = lambda t: np.array([[-1.,8*t],[2-4*t,-1.]])
    assert all(spectral_label(bad(t))[0] == 'stable' for t in (0.,.5,1.))
    assert spectral_label(bad(.25))[0] == 'unstable'
    assert inertia_check([bad(0),bad(1)],bad(.5))['label'] == 'pending'
    assert inertia_check([-np.eye(2)],-np.eye(2))['label'] == 'stable'
    assert inertia_check([np.diag([-1.,2.])],np.diag([-1.,2.]))['label'] == 'unstable'
    output = dict(schema_version='1.0', date='2026-10-03',
        scope='synthetic fixed-equilibrium multiaffine floating-point family; no original-algorithm claim',
        software=dict(python=platform.python_version(),numpy=np.__version__,scipy=scipy.__version__),
        analytic_tests=3, cases=[], provenance={})
    for x in (.1,.2,.4):
        family = Family(x)
        for lo,hi in ((.5,2.),(1.,3.)):
            values = tuple(float(z) for z in np.linspace(lo,hi,5))
            bounds = (lo,hi,lo,hi)
            case = dict(x_pu=x,bounds=list(bounds),validation=family.validation,methods={})
            for method in METHODS:
                ev = Evaluator(family,values)
                tic = time.perf_counter()
                rows = []
                for hidden in itertools.product(values,repeat=2):
                    row = ev.run(method,bounds,hidden)
                    reference,_ = spectral_label(family.raw(*hidden))
                    assert row['label'] == reference or row['label'] == 'pending'
                    row.update(hidden=list(hidden),reference=reference)
                    rows.append(row)
                case['methods'][method] = dict(rows=rows,
                    mean_requests=float(np.mean([r['requests'] for r in rows])),
                    pending=sum(r['label']=='pending' for r in rows),
                    mismatch=sum(r['label']!=r['reference'] and r['label']!='pending' for r in rows),
                    operations=dict(ev.counts), seconds=time.perf_counter()-tic)
            case['zero_query_condition'] = Evaluator(family,values).check(bounds)
            output['cases'].append(case)
            print(json.dumps(dict(x=x,box=[lo,hi],requests={
                m:round(case['methods'][m]['mean_requests'],3) for m in METHODS})),flush=True)
    for name in ('backend/core/average_dq_model.py','backend/core/average_dq_presets.py',
                 'backend/domain/average_dq_models.py',
                 'experiments/average-dq/run_parameter_information_pilot.py'):
        output['provenance'][name] = hashlib.sha256((ROOT/name).read_bytes()).hexdigest()
    output['seconds'] = time.perf_counter()-START
    destination = ROOT/'results/parameter-information-pilot/pilot.json'
    destination.parent.mkdir(parents=True,exist_ok=True)
    destination.write_text(json.dumps(output,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    print('V1_PILOT_FINISHED',flush=True)


if __name__ == '__main__':
    main()
