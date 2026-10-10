"""Quadratic power expansion and sampled convex inner approximation.

This is a standard DC linearization, not an optimizer or a new method.
Floating-point checks do not establish continuous-time feasibility.
"""
from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class PowerQuadratic:
    Q: np.ndarray
    q: np.ndarray
    r: np.ndarray

    def value(self, z):
        z = np.asarray(z, dtype=float)
        return np.einsum("i,mij,j->m", z, self.Q, z) + self.q @ z + self.r

    def gradient(self, z):
        return 2 * np.einsum("mij,j->mi", self.Q, z) + self.q


def expand_power(a, A, b, B, grid_voltage, alpha, beta, correction):
    """For i=a+Az, v=b+Bz, expand (alpha*v+beta*Vg+kappa*i) dot i.

    Arrays have shapes (time, dq), (time, dq, variable). Grid voltage
    may be common to all times or have shape (time, dq).
    """
    a, A, b, B = [np.asarray(x, dtype=float) for x in (a, A, b, B)]
    if a.ndim != 2 or a.shape[1] != 2 or b.shape != a.shape:
        raise ValueError("Expected matching real dq offsets")
    if A.ndim != 3 or A.shape[:2] != a.shape or B.shape != A.shape:
        raise ValueError("Expected matching affine dq maps")
    vg = np.broadcast_to(np.asarray(grid_voltage, dtype=float), a.shape)
    if not all(np.all(np.isfinite(x)) for x in (a, A, b, B, vg)):
        raise ValueError("Nonfinite affine data")
    if not np.all(np.isfinite([alpha, beta, correction])):
        raise ValueError("Nonfinite power coefficients")
    cross = np.einsum("mai,maj->mij", A, B)
    Q = alpha * (cross + cross.transpose(0, 2, 1)) / 2
    Q += correction * np.einsum("mai,maj->mij", A, A)
    q = alpha * (np.einsum("mai,ma->mi", A, b) + np.einsum("mai,ma->mi", B, a))
    q += beta * np.einsum("mai,ma->mi", A, vg)
    q += 2 * correction * np.einsum("mai,ma->mi", A, a)
    r = alpha * np.sum(a*b, axis=1) + beta * np.sum(vg*a, axis=1)
    r += correction * np.sum(a*a, axis=1)
    return PowerQuadratic(Q, q, r)


@dataclass(frozen=True)
class PowerInnerApproximation:
    power: PowerQuadratic
    positive: np.ndarray
    negative: np.ndarray
    reference: np.ndarray
    diagnostics: dict

    def value(self, z):
        z = np.asarray(z, dtype=float)
        ref = self.reference
        linear = 2*np.einsum("i,mij,j->m", ref, self.positive, z)
        constant = np.einsum("i,mij,j->m", ref, self.positive, ref)
        return linear - constant - np.einsum("i,mij,j->m", z, self.negative, z) + self.power.q @ z + self.power.r

    def gradient(self, z):
        return 2*np.einsum("mij,j->mi", self.positive, self.reference) - 2*np.einsum("mij,j->mi", self.negative, z) + self.power.q

    def gap(self, z):
        delta = np.asarray(z, dtype=float) - self.reference
        return np.einsum("i,mij,j->m", delta, self.positive, delta)


def make_inner_approximation(power, reference, relative_tolerance=1e-10):
    """Split every eigenvalue by sign; do not discard small eigenvalues.

    The tolerance validates numerical reconstruction/PSD, never relaxes a
    physical constraint. Guarantees apply only to the supplied sample times.
    """
    Q, q, r = power.Q, power.q, power.r
    ref = np.asarray(reference, dtype=float)
    if Q.ndim != 3 or Q.shape[1] != Q.shape[2] or q.shape != Q.shape[:2] or r.shape != Q.shape[:1]:
        raise ValueError("Invalid quadratic dimensions")
    if ref.shape != Q.shape[1:2] or not all(np.all(np.isfinite(x)) for x in (Q, q, r, ref)):
        raise ValueError("Invalid reference or quadratic values")
    if not np.isfinite(relative_tolerance) or not 0 < relative_tolerance < 1:
        raise ValueError("Invalid numerical verification tolerance")
    scale = max(1., float(np.max(np.abs(Q))))
    if np.max(np.abs(Q-Q.transpose(0, 2, 1))) > relative_tolerance*scale:
        raise ValueError("Quadratic matrix is not symmetric")
    eigenvalues, vectors = np.linalg.eigh(Q)
    pos = np.einsum("mik,mk,mjk->mij", vectors, np.maximum(eigenvalues, 0), vectors)
    neg = np.einsum("mik,mk,mjk->mij", vectors, np.maximum(-eigenvalues, 0), vectors)
    error = float(np.max(np.abs(Q-(pos-neg))))
    min_pos = float(np.min(np.linalg.eigvalsh(pos)))
    min_neg = float(np.min(np.linalg.eigvalsh(neg)))
    if error > relative_tolerance*scale or min(min_pos, min_neg) < -relative_tolerance*scale:
        raise ArithmeticError("Spectral split failed numerical checks")
    diagnostics = dict(reconstruction_error=error, positive_min_eigenvalue=min_pos,
                       negative_min_eigenvalue=min_neg, matrix_scale=scale,
                       relative_check_tolerance=relative_tolerance,
                       small_eigenvalues_discarded=False, continuous_time_proof=False)
    return PowerInnerApproximation(power, pos, neg, ref.copy(), diagnostics)
