"""Independent polynomial reconstruction of hypothetical LC hardware demands.

This does not run an optimizer or certify hardware ratings. Extrema use
floating-point polynomial roots and are not interval-arithmetic bounds.
"""
from __future__ import annotations

import numpy as np
from scipy.interpolate import BSpline, PPoly

from verify_constrained_ocp import Poly, extrema, norm_squared, rotate, vector_value

K = np.array([[0., -1.], [1., 0.]])
VG = np.array([1., 0.])
CF, X1, R1 = .02, .1, .01
DEGREE = 5


def _validate(knots, coefficients, case):
    knots, coefficients = np.asarray(knots, float), np.asarray(coefficients, float)
    if knots.ndim != 1 or len(knots) < 12 or not np.all(np.isfinite(knots)):
        raise ValueError("Invalid finite quintic knot vector")
    if np.any(np.diff(knots) < 0) or knots[5] != 0 or knots[-6] <= 0:
        raise ValueError("Knots must be sorted with a positive horizon starting at zero")
    if not np.all(knots[:6] == knots[0]) or not np.all(knots[-6:] == knots[-1]):
        raise ValueError("This endpoint audit requires clamped quintic knots")
    if coefficients.shape != (len(knots)-6, 2) or not np.all(np.isfinite(coefficients)):
        raise ValueError("Invalid finite two-axis coefficient matrix")
    for key in ["rt", "lt", "wb"]:
        if not np.isfinite(case[key]) or (key in ["lt", "wb"] and case[key] <= 0):
            raise ValueError(f"Invalid case parameter: {key}")
    for key in ["i0", "iss", "frozen"]:
        value = np.asarray(case[key], float)
        if value.shape != (2,) or not np.all(np.isfinite(value)):
            raise ValueError(f"Invalid case vector: {key}")
    return knots, coefficients


def _absolute_residual(polys):
    return max(max(abs(lo), abs(hi)) for lo, hi, _, _ in (extrema(p) for p in polys))


def hardware_audit(knots, coefficients, case):
    """Return a summary and per-segment extrema from saved physical-time knots."""
    knots, coefficients = _validate(knots, coefficients, case)
    spline = BSpline(knots, coefficients, DEGREE)
    pp = [PPoly.from_spline((knots, coefficients[:, axis], DEGREE)) for axis in range(2)]
    wb, lt, rt = float(case["wb"]), float(case["lt"]), float(case["rt"])
    rows, endpoint_states = [], []
    representation_errors = {key: 0. for key in ["i2", "vc", "i1", "vi"]}
    equation_errors = {key: 0. for key in ["RL", "capacitor", "inverter_inductor"]}
    dense_peaks = {key: 0. for key in representation_errors}
    dense_count = 0
    for j, (left, right) in enumerate(zip(pp[0].x[:-1], pp[0].x[1:])):
        width = float(right-left)
        if width <= 0:
            continue
        i2 = [Poly(component.c[:, j][::-1]*width**np.arange(6)) for component in pp]
        di2, ki2 = [p.deriv()/width for p in i2], rotate(i2)
        vc = [VG[a]+rt*i2[a]+lt*ki2[a]+lt/wb*di2[a] for a in range(2)]
        dvc, kvc = [p.deriv()/width for p in vc], rotate(vc)
        i1 = [i2[a]+CF/wb*dvc[a]+CF*kvc[a] for a in range(2)]
        di1, ki1 = [p.deriv()/width for p in i1], rotate(i1)
        vi = [vc[a]+R1*i1[a]+X1*ki1[a]+X1/wb*di1[a] for a in range(2)]
        fields = dict(i2=i2, vc=vc, i1=i1, vi=vi)
        residuals = dict(
            RL=[di2[a]-wb/lt*(vc[a]-VG[a]-rt*i2[a])+wb*ki2[a] for a in range(2)],
            capacitor=[dvc[a]-wb/CF*(i1[a]-i2[a])+wb*kvc[a] for a in range(2)],
            inverter_inductor=[di1[a]-wb/X1*(vi[a]-vc[a]-R1*i1[a])+wb*ki1[a] for a in range(2)])
        row = dict(start_s=float(left), end_s=float(right), extrema={}, equation_residuals_pu_per_s={})
        for key, vector in fields.items():
            _, maximum_squared, _, where = extrema(norm_squared(vector))
            row["extrema"][key] = dict(peak_pu=float(np.sqrt(max(0., maximum_squared))),
                                        peak_time_s=float(left+width*where))
        row.update(inverter_current_peak_pu=row["extrema"]["i1"]["peak_pu"],
                   inverter_current_peak_at_s=row["extrema"]["i1"]["peak_time_s"],
                   inverter_voltage_peak_pu=row["extrema"]["vi"]["peak_pu"],
                   inverter_voltage_peak_at_s=row["extrema"]["vi"]["peak_time_s"])
        for key, residual in residuals.items():
            value = _absolute_residual(residual)
            row["equation_residuals_pu_per_s"][key] = value
            equation_errors[key] = max(equation_errors[key], value)
        local = np.linspace(0, 1, 257)
        times = left+width*local
        dense_count += len(times)
        ii, di, ddi, dddi = (spline(times, nu=k) for k in range(4))
        vv = VG+rt*ii+lt*(ii@K.T)+lt/wb*di
        dvv = rt*di+lt*(di@K.T)+lt/wb*ddi
        ddvv = rt*ddi+lt*(ddi@K.T)+lt/wb*dddi
        ii1 = ii+CF/wb*dvv+CF*(vv@K.T)
        dii1 = di+CF/wb*ddvv+CF*(dvv@K.T)
        vvi = vv+R1*ii1+X1*(ii1@K.T)+X1/wb*dii1
        for key, direct in dict(i2=ii, vc=vv, i1=ii1, vi=vvi).items():
            from_poly = np.column_stack([p(local) for p in fields[key]])
            representation_errors[key] = max(representation_errors[key], float(np.max(np.abs(from_poly-direct))))
            peak = float(np.linalg.norm(direct, axis=1).max())
            dense_peaks[key] = max(dense_peaks[key], peak)
            if peak > row["extrema"][key]["peak_pu"]+1e-7:
                raise AssertionError(f"Polynomial extrema missed dense {key} peak")
        endpoint_states.append((vector_value(i1, 0), vector_value(i1, 1)))
        rows.append(row)
    if not rows:
        raise ValueError("No positive-length spline segment")
    if max(representation_errors.values()) > 1e-7:
        raise AssertionError(f"Spline / polynomial mismatch: {representation_errors}")
    if max(equation_errors.values()) > 1e-7:
        raise AssertionError(f"LC reconstruction equation residual: {equation_errors}")
    start_expected = np.asarray(case["i0"])+CF*K@np.asarray(case["frozen"])
    end_v = VG+rt*np.asarray(case["iss"])+lt*K@np.asarray(case["iss"])
    end_expected = np.asarray(case["iss"])+CF*K@end_v
    endpoints = dict(start_i1=endpoint_states[0][0].tolist(),
                     frozen_segment_i1=start_expected.tolist(),
                     start_i1_error_pu=float(np.linalg.norm(endpoint_states[0][0]-start_expected)),
                     end_i1=endpoint_states[-1][1].tolist(),
                     steady_i1=end_expected.tolist(),
                     end_i1_error_pu=float(np.linalg.norm(endpoint_states[-1][1]-end_expected)),
                     maximum_internal_i1_jump_pu=max((float(np.linalg.norm(a[1]-b[0])) for a,b in zip(endpoint_states[:-1], endpoint_states[1:])), default=0.))
    summary = dict(hypothetical_hardware=dict(Cf_pu=CF, X1_pu=X1, R1_pu=R1, Rf_pu=0.),
                   full_horizon_extrema={}, endpoint_check=endpoints,
                   equation_residuals_pu_per_s=equation_errors,
                   representation_errors_pu=representation_errors,
                   dense_check=dict(points=dense_count, peaks_pu=dense_peaks),
                   hardware_ratings_evaluated=False,
                   scope="Floating-point hypothetical LC demand reconstruction; not physical ratings, causality or control-bandwidth validation")
    for key in representation_errors:
        winner = max(rows, key=lambda r:r["extrema"][key]["peak_pu"])
        summary["full_horizon_extrema"][key] = winner["extrema"][key]
    summary["i1_peak_pu"] = summary["full_horizon_extrema"]["i1"]["peak_pu"]
    summary["i1_peak_time_s"] = summary["full_horizon_extrema"]["i1"]["peak_time_s"]
    summary["vi_peak_pu"] = summary["full_horizon_extrema"]["vi"]["peak_pu"]
    summary["vi_peak_time_s"] = summary["full_horizon_extrema"]["vi"]["peak_time_s"]
    summary.update(inverter_current_peak_pu=summary["i1_peak_pu"],
                   inverter_current_peak_at_s=summary["i1_peak_time_s"],
                   inverter_voltage_peak_pu=summary["vi_peak_pu"],
                   inverter_voltage_peak_at_s=summary["vi_peak_time_s"],
                   maximum_representation_difference=max(representation_errors.values()),
                   endpoint_inverter_current_errors=dict(start=endpoints["start_i1_error_pu"], end=endpoints["end_i1_error_pu"]),
                   equation_residuals=equation_errors)
    return summary, rows
