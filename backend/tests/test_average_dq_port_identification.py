import unittest

import numpy as np
from numpy.testing import assert_allclose

from backend.core.average_dq_model import (
    AverageDQModelError,
    build_average_dq_model,
)
from backend.core.average_dq_port_identification import (
    estimate_fundamental_phasor,
    identify_port_admittance_with_sinestream,
)
from backend.core.average_dq_presets import (
    build_average_dq_ablation_anchor_case,
    build_average_dq_verification_case,
)


class AverageDQPortIdentificationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        topology, parameters = build_average_dq_verification_case()
        cls.model = build_average_dq_model(topology, parameters)

    def test_harmonic_least_squares_recovers_complex_phasors(self) -> None:
        frequency_hz = 3.0
        time_s = np.arange(512, dtype=np.float64) / (frequency_hz * 128.0)
        expected = np.array([0.3 - 0.4j, -0.7 + 0.2j])
        samples = (
            np.array([1.2, -0.4])
            + np.real(
                np.exp(1j * 2.0 * np.pi * frequency_hz * time_s[:, None])
                * expected[None, :]
            )
        )
        phasor, residual = estimate_fundamental_phasor(
            time_s, samples, frequency_hz
        )

        assert_allclose(phasor, expected, atol=2.0e-15)
        self.assertLess(residual, 2.0e-14)

    def test_three_frequency_nonlinear_identification_meets_frozen_limits(
        self,
    ) -> None:
        study = identify_port_admittance_with_sinestream(self.model)

        self.assertTrue(study.passed)
        self.assertGreater(study.device_open_port_spectral_abscissa_per_s, 0.0)
        self.assertEqual(
            [point.frequency_hz for point in study.points], [0.2, 2.0, 20.0]
        )
        for point in study.points:
            self.assertTrue(point.passed)
            self.assertLess(
                point.maximum_magnitude_relative_error,
                study.magnitude_error_limit,
            )
            self.assertLess(
                point.maximum_phase_error_deg, study.phase_error_limit_deg
            )
            self.assertLess(
                point.maximum_harmonic_residual_ratio,
                study.harmonic_residual_limit,
            )
            self.assertLess(
                point.voltage_matrix_condition_number,
                study.voltage_matrix_condition_limit,
            )
            assert_allclose(
                point.device_current_phasor_matrix_pu,
                point.identified_admittance_pu
                @ point.pcc_voltage_phasor_matrix_pu,
                rtol=2.0e-12,
                atol=2.0e-12,
            )

    def test_identification_is_insensitive_to_halved_small_signal_amplitude(
        self,
    ) -> None:
        baseline = identify_port_admittance_with_sinestream(
            self.model, [2.0], source_amplitude_pu=1.0e-4
        ).points[0]
        halved = identify_port_admittance_with_sinestream(
            self.model, [2.0], source_amplitude_pu=5.0e-5
        ).points[0]

        assert_allclose(
            halved.identified_admittance_pu,
            baseline.identified_admittance_pu,
            rtol=8.0e-4,
            atol=2.0e-4,
        )

    def test_unstable_closed_loop_and_invalid_contract_are_rejected(self) -> None:
        topology, parameters = build_average_dq_ablation_anchor_case()
        unstable_model = build_average_dq_model(topology, parameters)

        with self.assertRaisesRegex(AverageDQModelError, "渐近稳定"):
            identify_port_admittance_with_sinestream(unstable_model, [2.0])
        with self.assertRaisesRegex(AverageDQModelError, "严格递增"):
            identify_port_admittance_with_sinestream(self.model, [2.0, 2.0])
        with self.assertRaisesRegex(AverageDQModelError, "两个完整测量周期"):
            identify_port_admittance_with_sinestream(
                self.model, [2.0], measurement_periods=1
            )


if __name__ == "__main__":
    unittest.main()
