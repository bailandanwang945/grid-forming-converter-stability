"""Eliminate four inverter-input endpoint equalities, without optimization.

Only input values are connected. Input slew, DC dynamics, causality, and
modulation constraints are not implied by these affine coordinates.
"""
from copy import copy

import numpy as np
from scipy.linalg import lstsq, null_space
from scipy.interpolate import BSpline

from run_constrained_ocp import T
from run_lc_voltage_envelope import CF, X1, R1, lc_matrices
from run_power_feasibility import K, VG
from run_scaled_ocp import ScaledProblem


def endpoint_targets(case):
    """Frozen-segment and steady-state inverter input, in the same dq frame."""
    for key in ["wb", "lt", "rt"]:
        if not np.isfinite(case[key]) or (key != "rt" and case[key] <= 0):
            raise ValueError(f"Invalid {key}")
    i0, iss, frozen = [np.asarray(case[key], float) for key in ["i0", "iss", "frozen"]]
    if any(v.shape != (2,) or not np.all(np.isfinite(v)) for v in [i0, iss, frozen]):
        raise ValueError("Invalid endpoint state")
    wb, lt, rt = case["wb"], case["lt"], case["rt"]
    a = -wb*rt/lt*np.eye(2)-wb*K
    di0 = a@i0+wb/lt*(frozen-VG)
    i1_before = i0+CF*K@frozen
    initial = frozen+R1*i1_before+X1*K@i1_before+X1/wb*di0
    vc_end = VG+rt*iss+lt*K@iss
    i1_end = iss+CF*K@vc_end
    final = vc_end+R1*i1_end+X1*K@i1_end
    return np.stack([initial, final]), dict(start_i2_third_derivative=a@a@di0,
                                           end_i2_third_derivative=np.zeros(2))


class ConnectedScaledProblem(ScaledProblem):
    """Original scaled z = anchor + null_basis @ connected y."""
    def __init__(self, old, seed):
        seed = np.asarray(seed, float)
        n = len(old.x0)
        if seed.shape != (n,) or not np.all(np.isfinite(seed)):
            raise ValueError("Invalid original-coordinate seed")
        if old.transform.shape != (old.base.nvar, n) or not np.all(np.isfinite(old.transform)):
            raise ValueError("Invalid original scaled transform")
        self.old = old
        target, _ = endpoint_targets(old.case)
        matrices = lc_matrices(old.base, np.array([0., T]))
        self.E = (matrices["vij"]@old.transform).reshape(4, n)
        original_offset = matrices["vi0"]+matrices["vij"]@old.base.x0
        self.target = (target-original_offset).ravel()
        increment, _, rank, singular_values = lstsq(self.E, self.target-self.E@seed, cond=1e-12)
        if rank != 4:
            raise ValueError(f"Endpoint equalities must have rank four, got {rank}")
        self.anchor = seed+increment
        self.null_basis = null_space(self.E, rcond=1e-12)
        if self.null_basis.shape != (n, n-4):
            raise ArithmeticError("Unexpected null-space dimension")
        equation_error = float(np.max(np.abs(self.E@self.anchor-self.target)))
        null_error = float(np.max(np.abs(self.E@self.null_basis)))
        orthogonal_error = float(np.max(np.abs(self.null_basis.T@self.null_basis-np.eye(n-4))))
        if max(equation_error, null_error, orthogonal_error) > 1e-8:
            raise ArithmeticError("Endpoint coordinate construction failed")
        # Never mutate old.base; this offset is essential to conic field assembly.
        self.base = copy(old.base)
        self.base.x0 = old.base.x0+old.transform@self.anchor
        self.transform = old.transform@self.null_basis
        self.scale = old.scale
        self.case, self.knots, self.times = self.base.case, self.base.knots, self.base.times
        self.x0 = np.zeros(n-4)
        self.diagnostics = dict(original_variable_count=n, connected_variable_count=n-4, endpoint_rank=int(rank),
                                singular_values=singular_values.tolist(), equality_residual=equation_error,
                                null_space_residual=null_error, null_space_orthogonality_residual=orthogonal_error,
                                projection_distance=float(np.linalg.norm(increment)),
                                anchor=self.anchor.tolist(), null_basis=self.null_basis.tolist(),
                                transform=self.transform.tolist(),
                                scope="Input endpoint values connected; no input-rate or hardware guarantee")
        audit = endpoint_input_audit(self.knots*T, self.coefficients(self.x0), self.case)
        if max(audit["inverter_input_errors_pu"].values()) > 1e-7:
            raise ArithmeticError("Independent spline endpoint input mismatch")

    def original_coordinates(self, y):
        y = np.asarray(y, float)
        if y.shape != self.x0.shape or not np.all(np.isfinite(y)):
            raise ValueError("Invalid connected coordinate")
        return self.anchor+self.null_basis@y

    def physical(self, y):
        y = np.asarray(y, float)
        if y.shape != self.x0.shape or not np.all(np.isfinite(y)):
            raise ValueError("Invalid connected coordinate")
        return self.base.x0+self.transform@y


def endpoint_input_audit(knots, coefficients, case):
    """Recompute endpoint vi from direct BSpline derivatives, not E residuals."""
    knots, coefficients = np.asarray(knots, float), np.asarray(coefficients, float)
    if knots.ndim != 1 or len(knots) < 12 or np.any(~np.isfinite(knots)) or np.any(np.diff(knots)<0):
        raise ValueError("Invalid knot vector")
    if coefficients.shape != (len(knots)-6, 2) or not np.all(np.isfinite(coefficients)):
        raise ValueError("Invalid spline coefficients")
    if knots[5] != 0 or abs(knots[-6]-T)>1e-12:
        raise ValueError("This audit requires the fixed 60 ms horizon")
    targets, derivative_targets = endpoint_targets(case)
    spline = BSpline(knots, coefficients, 5)
    wb, lt, rt = case["wb"], case["lt"], case["rt"]
    actual, third_errors = [], []
    for t, ddd_target in zip([0., T], derivative_targets.values()):
        i, di, ddi, dddi = [spline(t, nu=k) for k in range(4)]
        vc = VG+rt*i+lt*K@i+lt/wb*di
        dvc = rt*di+lt*K@di+lt/wb*ddi
        ddvc = rt*ddi+lt*K@ddi+lt/wb*dddi
        i1 = i+CF/wb*dvc+CF*K@vc
        di1 = di+CF/wb*ddvc+CF*K@dvc
        vi = vc+R1*i1+X1*K@i1+X1/wb*di1
        actual.append(vi)
        third_errors.append(float(np.linalg.norm(dddi-ddd_target)))
    errors = np.linalg.norm(np.asarray(actual)-targets, axis=1)
    return dict(actual_inverter_inputs_pu=np.asarray(actual).tolist(), target_inverter_inputs_pu=targets.tolist(),
                inverter_input_errors_pu=dict(start=float(errors[0]), end=float(errors[1])),
                i2_third_derivative_errors_pu_per_s3=dict(start=third_errors[0], end=third_errors[1]),
                input_endpoint_pass=bool(np.max(errors)<=1e-7),
                scope="Endpoint inverter input voltage continuity only; not derivative continuity or ratings validation")
