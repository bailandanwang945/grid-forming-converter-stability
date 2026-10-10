"""Analytic and independent numerical checks for the isolated VI pilot.

Run: python experiments/average-dq/test_virtual_reactance_frequency_pilot.py
Failures return nonzero via unittest; no physical-model or novelty assertion.
"""

import unittest
from types import SimpleNamespace

import numpy as np
from scipy.integrate import solve_ivp

from run_virtual_reactance_frequency_pilot import (
    J,
    STEPS,
    VARIANTS,
    analytic_difference,
    build_point,
    compare_labels,
    independent_command,
    jacobian,
    relative_error,
    sampled_command_matrices,
    variant_rhs,
)


class VirtualReactanceFrequencyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.model = build_point(0.2, 0.3)

    def test_general_state_exact_bilinear_rhs_and_all_downstream_channels(self):
        model = self.model
        x = model.operating_point.state.copy()
        x[1], x[8:10] = 0.017, [0.4, -0.23]
        p = model.parameters
        dv = p.virtual_reactance_pu * x[1] * np.array([0.23, 0.4])
        expected = np.zeros(16)
        expected[10:12] = p.voltage_integral_gain_per_s * dv
        expected[12:14] = (
            p.current_integral_gain_per_s * p.voltage_proportional_gain_pu * dv
        )
        expected[14:16] = (
            p.current_proportional_gain_pu
            * p.voltage_proportional_gain_pu
            * dv
            / p.modulation_time_constant_s
        )
        observed = variant_rhs(x, model, VARIANTS[1]) - variant_rhs(
            x, model, VARIANTS[0]
        )
        np.testing.assert_allclose(observed, expected, rtol=1e-11, atol=1e-10)
        self.assertEqual(np.count_nonzero(expected), 6)
        np.testing.assert_array_equal(observed[:10], 0.0)

    def test_pending_pair_is_not_a_definite_disagreement(self):
        for labels in [
            ("stable", "numerical-pending"),
            ("unstable", "numerical-pending"),
            ("numerical-pending", "numerical-pending"),
        ]:
            result = compare_labels(labels)
            self.assertEqual(result["comparison_status"], "numerical-pending")
            self.assertIsNone(result["classification_disagreement"])
        self.assertTrue(
            compare_labels(["stable", "unstable"])["classification_disagreement"]
        )
        self.assertFalse(
            compare_labels(["stable", "stable"])["classification_disagreement"]
        )

    def test_general_state_analytic_jacobian_from_nonlinear_rhs_two_steps(self):
        model = self.model
        x = model.operating_point.state.copy()
        x[1], x[8:10] = 0.021, [0.51, -0.16]
        expected = analytic_difference(x, model.parameters)
        self.assertGreater(np.linalg.norm(expected[:, 8:10]), 0)
        for step in STEPS:
            observed = jacobian(
                lambda z: (
                    variant_rhs(z, model, VARIANTS[1])
                    - variant_rhs(z, model, VARIANTS[0])
                ),
                x,
                step,
            )
            self.assertLess(relative_error(observed, expected), 2e-7)

    def test_common_nominal_equilibrium_and_baseline_production_jacobian(self):
        model = self.model
        x = model.operating_point.state
        for variant in VARIANTS:
            self.assertLess(np.max(abs(variant_rhs(x, model, variant))), 1e-7)
        np.testing.assert_array_equal(
            variant_rhs(x, model, VARIANTS[0]), variant_rhs(x, model, VARIANTS[1])
        )
        baseline = jacobian(lambda z: variant_rhs(z, model, VARIANTS[0]), x, STEPS[0])
        self.assertLess(
            relative_error(baseline, model.linearization.closed_state_matrix), 2e-7
        )

    def test_equilibrium_difference_frequency_column_has_all_controller_channels(self):
        model = self.model
        expected = analytic_difference(model.operating_point.state, model.parameters)
        other = expected.copy()
        other[:, 1] = 0
        np.testing.assert_array_equal(other, 0)
        for rows in [slice(10, 12), slice(12, 14), slice(14, 16)]:
            self.assertGreater(np.linalg.norm(expected[rows, 1]), 0)

    def test_zero_Xv_control_at_off_equilibrium_nonzero_frequency(self):
        model = build_point(0.4, 0.0)
        x = model.operating_point.state.copy()
        x[1] = -0.04
        x[8:10] = [0.6, -0.2]
        np.testing.assert_array_equal(
            variant_rhs(x, model, VARIANTS[0]), variant_rhs(x, model, VARIANTS[1])
        )
        np.testing.assert_array_equal(analytic_difference(x, model.parameters), 0)

    def test_zero_current_rhs_control_and_nominal_jacobian_control(self):
        model = self.model
        x = model.operating_point.state.copy()
        x[8:10] = 0
        x[1] = 0.03
        np.testing.assert_array_equal(
            variant_rhs(x, model, VARIANTS[0]), variant_rhs(x, model, VARIANTS[1])
        )
        # Zero current alone does not kill the derivative with respect to current.
        self.assertGreater(np.linalg.norm(analytic_difference(x, model.parameters)), 0)
        x[1] = 0.0
        observed = jacobian(
            lambda z: (
                variant_rhs(z, model, VARIANTS[1]) - variant_rhs(z, model, VARIANTS[0])
            ),
            x,
            STEPS[0],
        )
        np.testing.assert_allclose(observed, 0, atol=1e-7)

    def test_capacitor_and_inductor_frequency_cross_terms_retained(self):
        # Independent synthetic coefficients isolate the two non-VI omega terms.
        p = SimpleNamespace(
            reactive_power_voltage_droop_pu=0.0,
            virtual_resistance_pu=0.0,
            virtual_reactance_pu=0.0,
            filter_capacitor_susceptance_pu=0.17,
            voltage_proportional_gain_pu=0.4,
            converter_side_resistance_pu=0.03,
            converter_side_reactance_pu=0.2,
            current_proportional_gain_pu=0.7,
        )
        converter = SimpleNamespace(
            voltage_setpoint_pu=1.0, reactive_power_setpoint_pu=0.1
        )
        x = np.linspace(-0.4, 0.7, 14)
        expected = (
            p.converter_side_reactance_pu * J @ x[4:6]
            + p.current_proportional_gain_pu
            * p.filter_capacitor_susceptance_pu
            * J
            @ x[6:8]
        )
        for variant in VARIANTS:
            f = jacobian(
                lambda z: independent_command(z, p, converter, variant), x, STEPS[0]
            )
            np.testing.assert_allclose(f[:, 1], expected, rtol=1e-8, atol=1e-9)

    def test_independent_command_reconstructs_all_sixteen_lag_states(self):
        model = self.model
        x, p = model.operating_point.state, model.parameters
        for variant in VARIANTS:
            a = jacobian(lambda z: variant_rhs(z, model, variant), x, STEPS[0])
            f = jacobian(
                lambda z: independent_command(z, p, model.converter, variant),
                x[:14],
                STEPS[0],
            )
            reconstructed = np.block(
                [
                    [a[:14, :14], a[:14, 14:]],
                    [
                        f / p.modulation_time_constant_s,
                        -np.eye(2) / p.modulation_time_constant_s,
                    ],
                ]
            )
            self.assertLess(relative_error(reconstructed, a), 2e-7)

    def test_sampled_map_analytic_singular_plant_and_complete_delay_buffer(self):
        a0 = np.zeros((1, 1))
        b = np.ones((1, 1))
        f = np.array([[-3.0]])
        period = 0.5
        zero = sampled_command_matrices(a0, b, f, period, delay_steps=0).phi
        np.testing.assert_allclose(zero, [[-0.5]], atol=1e-14)
        delayed = sampled_command_matrices(a0, b, f, period, delay_steps=1).phi
        np.testing.assert_allclose(delayed, [[1.0, 0.5], [-3.0, 0.0]], atol=1e-14)
        roots = np.linalg.eigvals(delayed)
        np.testing.assert_allclose(roots**2 - roots + 1.5, 0, atol=1e-14)
        self.assertEqual(len(roots), 2)

    def test_period_map_against_independent_nonlinear_hold_integration(self):
        # Nonlinear local-dq envelope hold, not a second matrix exponential.
        model = self.model
        xstar, p = model.operating_point.state, model.parameters
        period, h = 0.0005, 5e-6
        for variant in VARIANTS:
            a = jacobian(lambda z: variant_rhs(z, model, variant), xstar, STEPS[0])
            f = jacobian(
                lambda z: independent_command(z, p, model.converter, variant),
                xstar[:14],
                STEPS[0],
            )
            for delay in (0, 1):
                phi = sampled_command_matrices(
                    a[:14, :14], a[:14, 14:], f, period, delay_steps=delay
                ).phi
                columns = [1, 8] if delay == 0 else [1, 8, 14]
                for column in columns:
                    endpoints = []
                    for sign in (-1, 1):
                        initial, held = xstar[:14].copy(), xstar[14:].copy()
                        if column < 14:
                            initial[column] += sign * h
                        else:
                            held[column - 14] += sign * h
                        if delay == 0:
                            held = independent_command(
                                initial, p, model.converter, variant
                            )
                        sol = solve_ivp(
                            lambda _t, z: variant_rhs(
                                np.concatenate([z, held]), model, variant
                            )[:14],
                            (0, period),
                            initial,
                            method="DOP853",
                            rtol=1e-11,
                            atol=1e-13,
                            max_step=period / 12,
                        )
                        self.assertTrue(sol.success, sol.message)
                        endpoint = sol.y[:, -1]
                        if delay:
                            queued = independent_command(
                                initial, p, model.converter, variant
                            )
                            endpoint = np.concatenate([endpoint, queued])
                        endpoints.append(endpoint)
                    observed = (endpoints[1] - endpoints[0]) / (2 * h)
                    self.assertLess(relative_error(observed, phi[:, column]), 2e-7)


if __name__ == "__main__":
    unittest.main()
