from __future__ import annotations

import unittest

from backend.core.delay_approximation_audit import (
    DelayApproximationError,
    pade_delay_coefficients,
    run_delay_approximation_audit,
)


class DelayApproximationAuditTest(unittest.TestCase):
    def test_python_control_reference_vectors(self) -> None:
        self.assertEqual(pade_delay_coefficients(1.0, 1), ([-1.0, 2.0], [1.0, 2.0]))
        self.assertEqual(
            pade_delay_coefficients(1.0, 2),
            ([1.0, -6.0, 12.0], [1.0, 6.0, 12.0]),
        )
        self.assertEqual(
            pade_delay_coefficients(1.0, 3),
            ([-1.0, 12.0, -60.0, 120.0], [1.0, 12.0, 60.0, 120.0]),
        )

    def test_zero_delay_and_zero_order_are_identity(self) -> None:
        self.assertEqual(pade_delay_coefficients(0.0, 3), ([1.0], [1.0]))
        self.assertEqual(pade_delay_coefficients(0.1, 0), ([1.0], [1.0]))

    def test_invalid_inputs_are_rejected(self) -> None:
        for delay, order in ((-1.0, 1), (float("inf"), 1), (1.0, -1), (1.0, True)):
            with self.subTest(delay=delay, order=order), self.assertRaises(
                DelayApproximationError
            ):
                pade_delay_coefficients(delay, order)

    def test_fixed_frequency_response_audit_passes(self) -> None:
        audit = run_delay_approximation_audit()
        self.assertEqual(audit["status"], "passed")
        summary = audit["band_summary"]
        self.assertTrue(summary["all_pade_poles_left_half_plane"])
        self.assertTrue(summary["phase_error_decreases_through_order_three"])
        self.assertFalse(audit["scope"]["closed_loop_poles_with_exact_delay_compared"])
        self.assertFalse(audit["scope"]["pade_poles_reported_as_physical_modes"])


if __name__ == "__main__":
    unittest.main()
