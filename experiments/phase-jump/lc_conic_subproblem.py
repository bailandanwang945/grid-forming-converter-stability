"""Explicit SOCP of a sampled power inner approximation; mature method.

Clarabel is imported only by solve(), so algebra tests need no new package.
The conic slack is not evidence of original nonlinear infeasibility.
"""
from dataclasses import dataclass

import numpy as np
from scipy import sparse

from power_inner_approximation import expand_power, make_inner_approximation
from run_lc_voltage_envelope import lc_matrices
from run_power_feasibility import VG


@dataclass
class ConicSubproblem:
    P: sparse.csc_matrix
    q: np.ndarray
    A: sparse.csc_matrix
    b: np.ndarray
    cone_specs: list
    groups: list
    power: object
    reference: np.ndarray
    diagnostics: dict

    def residuals(self, delta, slack):
        """Unscaled primal cone margins b-Ax; for implementation checks."""
        y = np.r_[delta, slack]
        vector = self.b-self.A@y
        out = []
        for g in self.groups:
            block = vector[g["start"]:g["end"]]
            margin = float(block[0]-np.linalg.norm(block[1:])) if g["kind"] == "soc" else float(block.min())
            out.append(dict(tag=g["tag"], margin=margin))
        return out


def build_subproblem(scaled, times, reference, voltage_limit=1.2, regularization=1e-8):
    ref = np.asarray(reference, dtype=float)
    times = np.asarray(times, dtype=float)
    n = len(scaled.x0)
    if ref.shape != (n,) or not np.all(np.isfinite(ref)):
        raise ValueError("Invalid scaled reference")
    if times.ndim != 1 or len(times) == 0 or np.any(~np.isfinite(times)) or np.any((times < 0) | (times > .06)):
        raise ValueError("Invalid constraint times")
    if not np.isfinite(voltage_limit) or voltage_limit <= 0 or not np.isfinite(regularization) or regularization <= 0:
        raise ValueError("Invalid conic settings")
    base, transform = scaled.base, scaled.transform
    maps = {**base.matrices(times), **lc_matrices(base, times)}
    fields = {}
    for key in ["i", "v", "i1", "vi"]:
        jac = maps[key+"j"] @ transform
        offset = maps[key+"0"]+maps[key+"j"] @ base.x0
        fields[key] = (offset, jac)
    c = scaled.case
    power = expand_power(*fields["i"], *fields["v"], VG, c["alpha"], c["beta"], c["correction"])
    inner = make_inner_approximation(power, ref)
    eigenvalues, vectors = np.linalg.eigh(power.Q)
    factors = np.sqrt(np.maximum(-eigenvalues, 0))[:, :, None] * vectors.transpose(0, 2, 1)
    factor_error = float(np.max(np.abs(factors.transpose(0, 2, 1) @ factors-inner.negative)))
    if factor_error > 1e-10*inner.diagnostics["matrix_scale"]:
        raise ArithmeticError("Negative-spectrum factor mismatch")
    pref, grad = power.value(ref), power.gradient(ref)
    matrices, offsets, specs, groups = [], [], [], []
    row_count = 0

    def add(kind, D, offset, tag):
        nonlocal row_count
        # D*x+offset belongs to cone => A=-D, b=offset.
        D, offset = np.asarray(D), np.asarray(offset)
        matrices.append(sparse.csc_matrix(-D))
        offsets.append(offset)
        specs.append((kind, len(offset)))
        groups.append(dict(kind=kind, start=row_count, end=row_count+len(offset), tag=tag))
        row_count += len(offset)

    limits = dict(i=1.3, v=float(np.linalg.norm(c["frozen"])), i1=1.3, vi=float(voltage_limit))
    for key, limit in limits.items():
        offset, jac = fields[key]
        at_ref = offset+jac @ ref
        for j in range(len(times)):
            D = np.zeros((3, n+1))
            D[0, -1] = limit
            D[1:, :-1] = jac[j]
            add("soc", D, np.r_[limit, at_ref[j]], f"{key}:{j}")
    for j in range(len(times)):
        # ||F*d||^2 <= u iff (u+1, 2F*d, u-1) belongs to SOC.
        u0 = pref[j]-c["ppre"]
        D = np.zeros((n+2, n+1))
        D[0, :-1] = D[-1, :-1] = grad[j]
        D[0, -1] = D[-1, -1] = 1.
        D[1:-1, :-1] = 2*factors[j]
        add("soc", D, np.r_[u0+1., np.zeros(n), u0-1.], f"power:{j}")
    D = np.zeros((1, n+1))
    D[0, -1] = 1.
    add("nonnegative", D, np.zeros(1), "slack")
    P = sparse.diags(np.r_[np.full(n, 2*regularization), 0.], format="csc")
    return ConicSubproblem(P, np.r_[np.zeros(n), 1.], sparse.vstack(matrices).tocsc(),
        np.concatenate(offsets), specs, groups, power, ref.copy(),
        dict(**inner.diagnostics, negative_factor_reconstruction_error=factor_error,
             sample_count=len(times), variable_count=n+1, conic_row_count=row_count,
             regularization=regularization, physical_limits=limits))


def solve(subproblem, seconds=15.):
    import clarabel

    if not np.isfinite(seconds) or seconds <= 0:
        raise ValueError("Invalid solver time budget")
    cones = [clarabel.SecondOrderConeT(dim) if kind == "soc" else clarabel.NonnegativeConeT(dim)
             for kind, dim in subproblem.cone_specs]
    settings = clarabel.DefaultSettings()
    settings.verbose = False
    settings.time_limit = float(seconds)
    settings.max_iter = 200
    settings.max_threads = 1
    settings.tol_gap_abs = settings.tol_gap_rel = settings.tol_feas = 1e-10
    solver = clarabel.DefaultSolver(subproblem.P, subproblem.q, subproblem.A, subproblem.b, cones, settings)
    result = solver.solve()
    x = np.asarray(result.x, dtype=float)
    state = dict(status=str(result.status), iterations=result.iterations, solve_seconds=result.solve_time,
                 objective=result.obj_val if np.isfinite(result.obj_val) else None,
                 primal_residual=result.r_prim if np.isfinite(result.r_prim) else None,
                 dual_residual=result.r_dual if np.isfinite(result.r_dual) else None)
    valid_candidate = str(result.status) in {"Solved", "AlmostSolved", "MaxIterations", "MaxTime", "InsufficientProgress"}
    valid_candidate = bool(valid_candidate and x.shape == subproblem.q.shape and np.all(np.isfinite(x)))
    return x if valid_candidate else None, state
