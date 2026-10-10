"""Same fixed voltage-tracking objective, with optional sampled power floor."""
from types import SimpleNamespace

import numpy as np
from scipy import sparse

from lc_conic_subproblem import build_subproblem


def objective_quadratic(problem, reference):
    base, c = problem.base, problem.physical(reference)
    _, v, dv = base.fields(c)
    Jv, Jdv = base.train["vj"] @ problem.transform, base.train["dvj"] @ problem.transform
    H = 2*np.einsum("m,mai,maj->ij", base.weights, Jv, Jv)
    H += 2e-4*np.einsum("m,mai,maj->ij", base.weights, Jdv, Jdv)
    q = 2*np.einsum("m,ma,mai->i", base.weights, v-base.reference, Jv)
    q += 2e-4*np.einsum("m,ma,mai->i", base.weights, dv, Jdv)
    return H/problem.scale, q/problem.scale, base.objective(c)/problem.scale


def build_objective_subproblem(problem, times, reference, hard_power):
    full = build_subproblem(problem, times, reference)
    selected = [group for group in full.groups if group["kind"] == "soc" and
                (hard_power or not group["tag"].startswith("power:"))]
    indices = np.concatenate([np.arange(group["start"], group["end"]) for group in selected])
    A, b = full.A[indices, :-1].tocsc(), full.b[indices]
    specs = [("soc", group["end"]-group["start"]) for group in selected]
    H, q, constant = objective_quadratic(problem, reference)
    error = float(np.max(np.abs(H-H.T)))
    eigen_min = float(np.min(np.linalg.eigvalsh(H)))
    if error > 1e-10 or eigen_min < -1e-10:
        raise ArithmeticError("Voltage objective Hessian check failed")
    return SimpleNamespace(P=sparse.triu(sparse.csc_matrix(H)).tocsc(), q=q, A=A, b=b, cone_specs=specs,
                           diagnostics=dict(**full.diagnostics, hard_power=hard_power, slack_variable=False,
                                            objective_H_min_eigenvalue=eigen_min, objective_H_symmetry_error=error,
                                            objective_constant_at_reference=constant))
