from __future__ import annotations

import unittest
from dataclasses import replace
from unittest.mock import patch

import numpy as np
from scipy.linalg import eig

from backend.core.average_dq_ablation import (
    ModalSignature,
    _aggregate_match_history,
    _combine_path_matches,
    match_mode,
    modal_signature,
)


def oscillator(real_part: float, imaginary_part: float) -> np.ndarray:
    """Return a real matrix with poles real_part +/- j*imaginary_part."""

    return np.array(
        [[real_part, -imaginary_part], [imaginary_part, real_part]],
        dtype=np.float64,
    )


class AverageDQAblationMatchingCounterexampleTest(unittest.TestCase):
    def test_complex_phase_and_amplitude_do_not_change_mac_or_identity(self):
        reference = modal_signature(np.diag([2.0, 1.0]), 1.0)
        rescaled = ModalSignature(
            eigenvalue_per_s=reference.eigenvalue_per_s,
            right_vector=(3.0 + 4.0j) * reference.right_vector,
            left_vector=(-0.2 + 0.7j) * reference.left_vector,
            right_residual=reference.right_residual,
            left_residual=reference.left_residual,
            condition_number=reference.condition_number,
        )

        original_match = match_mode(reference, np.diag([10.0, 1.05]))
        rescaled_match = match_mode(rescaled, np.diag([10.0, 1.05]))

        self.assertAlmostEqual(original_match.eigenvalue_per_s.real, 1.05)
        self.assertEqual(
            rescaled_match.eigenvalue_per_s,
            original_match.eigenvalue_per_s,
        )
        self.assertAlmostEqual(rescaled_match.right_mac, 1.0, places=12)
        self.assertAlmostEqual(rescaled_match.left_mac, 1.0, places=12)

    def test_candidate_eigenpair_permutation_does_not_change_match(self):
        reference = modal_signature(np.diag([2.0, 1.0]), 1.0)
        candidate = np.diag([10.0, 1.05])
        expected = match_mode(reference, candidate)
        eigenvalues, left_vectors, right_vectors = eig(
            candidate, left=True, right=True
        )
        permutation = np.array([1, 0])

        with patch(
            "backend.core.average_dq_ablation.eig",
            return_value=(
                eigenvalues[permutation],
                left_vectors[:, permutation],
                right_vectors[:, permutation],
            ),
        ):
            permuted = match_mode(reference, candidate)

        self.assertEqual(permuted.eigenvalue_per_s, expected.eigenvalue_per_s)
        self.assertAlmostEqual(permuted.right_mac, expected.right_mac, places=12)
        self.assertAlmostEqual(permuted.left_mac, expected.left_mac, places=12)

    def test_positive_imaginary_representative_does_not_flip_to_conjugate(self):
        reference_matrix = oscillator(-1.0, 2.0)
        reference = modal_signature(reference_matrix, -1.0 + 2.0j)

        match = match_mode(reference, oscillator(-0.8, 2.1))

        self.assertGreater(match.eigenvalue_per_s.imag, 0.0)
        self.assertAlmostEqual(match.eigenvalue_per_s.real, -0.8, places=12)
        self.assertAlmostEqual(match.eigenvalue_per_s.imag, 2.1, places=12)

    def test_real_part_crossing_does_not_change_mode_identity(self):
        reference = modal_signature(oscillator(-0.2, 2.0), -0.2 + 2.0j)

        match = match_mode(reference, oscillator(0.2, 2.0))

        self.assertGreater(match.eigenvalue_per_s.real, 0.0)
        self.assertGreater(match.eigenvalue_per_s.imag, 0.0)
        self.assertEqual(match.status, "matched")

    def test_strongly_nonnormal_mode_must_be_pending_by_condition_gate(self):
        nonnormal = np.array([[1.0, 1.0e10], [0.0, 2.0]], dtype=np.float64)
        reference = modal_signature(nonnormal, 1.0)

        match = match_mode(reference, nonnormal)

        # P1 target contract: ModeMatch must expose the biorthogonal
        # condition number and reject values above the default 1e8 gate.
        self.assertGreater(match.condition_number, 1.0e8)
        self.assertEqual(match.status, "pending")
        self.assertIn("condition", match.reason)

    def test_near_degenerate_pair_is_pending_without_subspace_tracking(self):
        reference = modal_signature(np.diag([1.0, 2.0]), 1.0)
        near_degenerate = np.diag([1.0, 1.0 + 1.0e-10])

        match = match_mode(reference, near_degenerate)

        self.assertEqual(match.status, "pending")
        self.assertIn("near-degenerate", match.reason)

    def test_pending_refinement_evidence_is_not_erased_by_later_success(self):
        reference = modal_signature(np.diag([2.0, 1.0]), 1.0)
        accepted = match_mode(reference, np.diag([2.0, 1.0]))
        exhausted = replace(
            accepted,
            status="pending",
            reason="eigenvalue-distance-above-threshold",
        )

        aggregate = _aggregate_match_history(
            reference,
            (exhausted, accepted),
            "synthetic-refinement",
        )

        self.assertEqual(aggregate.status, "pending")
        self.assertIn("eigenvalue-distance", aggregate.reason)
        self.assertEqual(aggregate.path_steps, 2)

    def test_two_path_endpoint_identity_conflict_is_pending(self):
        reference = modal_signature(np.diag([2.0, 1.0]), 1.0)
        first = match_mode(reference, np.diag([2.0, 1.0]))
        second = replace(first, eigenvalue_per_s=1.5 + 0.0j)

        combined = _combine_path_matches(first, second)

        self.assertEqual(combined.status, "pending")
        self.assertIn("path-dependent-identity", combined.reason)


if __name__ == "__main__":
    unittest.main()
