"""Analytic countercases and declared-model adapter checks, no saved outcomes."""

import json
import unittest
from dataclasses import replace
from types import SimpleNamespace

import numpy as np
from numpy.testing import assert_allclose

from backend.core.average_dq_model import J, _rotation, build_average_dq_model
from backend.core.average_dq_presets import build_average_dq_ablation_anchor_case
from backend.core.average_dq_sampled_command import (
    SampledCommandError,
    EXPECTED_STATE_LABELS,
    sampled_command_matrices,
    first_order_command_lag_matrix,
    split_average_dq_sampled_command,
    analyze_sampled_command_matrix,
    compare_average_dq_sampled_command,
)


class GenericSampledCommandTests(unittest.TestCase):
    def test_singular_plant_exact_hold(self):
        result = sampled_command_matrices([[0]], [[2]], [[-3]], 0.1)
        assert_allclose(result.E, [[1]])
        assert_allclose(result.Gamma, [[0.2]])
        assert_allclose(result.phi, [[0.4]])

    def test_delay_uses_old_buffer_not_new_or_next_state(self):
        result = sampled_command_matrices([[0]], [[1]], [[-2]], 0.1, delay_steps=1)
        assert_allclose(result.phi, [[1, 0.1], [-2, 0]])
        assert_allclose(result.phi @ np.array([3, 4]), [3.4, -6])

    def test_instantaneous_stable_but_sampled_unstable(self):
        # xdot=u, u[k]=-3*x[k], Ts=1: ideal rate -3, multiplier -2.
        phi = sampled_command_matrices([[0]], [[1]], [[-3]], 1).phi
        self.assertEqual(
            analyze_sampled_command_matrix([[-3]])["classification"], "stable"
        )
        self.assertEqual(
            analyze_sampled_command_matrix(phi, sampling_period_s=1)["classification"],
            "unstable",
        )
        self.assertAlmostEqual(
            analyze_sampled_command_matrix(phi, sampling_period_s=1)["metric_per_s"],
            np.log(2),
        )

    def test_full_delayed_spectrum_not_only_slow_branch(self):
        # No delay: multiplier -0.5 stable. One-step buffer roots have radius sqrt(1.5).
        undelayed = sampled_command_matrices([[0]], [[1]], [[-1.5]], 1)
        assert_allclose(undelayed.phi, [[-0.5]])
        self.assertEqual(
            analyze_sampled_command_matrix(undelayed.phi, sampling_period_s=1)[
                "classification"
            ],
            "stable",
        )
        unstable = sampled_command_matrices([[0]], [[1]], [[-1.5]], 1, delay_steps=1)
        self.assertEqual(unstable.phi.shape, (2, 2))
        self.assertEqual(
            analyze_sampled_command_matrix(unstable.phi, sampling_period_s=1)[
                "classification"
            ],
            "unstable",
        )

    def test_lag_sampled_disagreement_both_directions(self):
        # a=0, f=-3: phase-matched lag stable but sampled multiplier -2 unstable.
        lag = first_order_command_lag_matrix([[0]], [[1]], [[-3]], 0.5)
        sampled = sampled_command_matrices([[0]], [[1]], [[-3]], 1).phi
        self.assertEqual(
            analyze_sampled_command_matrix(lag)["classification"], "stable"
        )
        self.assertEqual(
            analyze_sampled_command_matrix(sampled, sampling_period_s=1)[
                "classification"
            ],
            "unstable",
        )
        # a=3; choose f analytically for sampled multiplier 0.5. Lag trace=1>0.
        f = 3 * (0.5 - np.exp(3)) / (np.exp(3) - 1)
        lag = first_order_command_lag_matrix([[3]], [[1]], [[f]], 0.5)
        sampled = sampled_command_matrices([[3]], [[1]], [[f]], 1).phi
        assert_allclose(sampled, [[0.5]], atol=1e-12)
        self.assertEqual(
            analyze_sampled_command_matrix(lag)["classification"], "unstable"
        )
        self.assertEqual(
            analyze_sampled_command_matrix(sampled, sampling_period_s=1)[
                "classification"
            ],
            "stable",
        )

    def test_zero_radius_pending_and_nonfinite_exponential_failure(self):
        zero = analyze_sampled_command_matrix([[0]], sampling_period_s=0.001)
        self.assertEqual(zero["classification"], "numerical-pending")
        self.assertIsNone(zero["metric_per_s"])
        json.dumps(zero, allow_nan=False)
        for a, period in [([[1000]], 1), ([[1e308]], 1e308)]:
            with (
                self.subTest(a=a, period=period),
                self.assertRaises(SampledCommandError),
            ):
                sampled_command_matrices(a, [[1]], [[1]], period)

    def test_near_boundary_tiny_period_and_step_uncertainty(self):
        self.assertEqual(
            analyze_sampled_command_matrix([[1]], sampling_period_s=0.001)[
                "classification"
            ],
            "numerical-pending",
        )
        tiny = analyze_sampled_command_matrix([[0.99999]], sampling_period_s=1e-10)
        self.assertIn(
            "tiny-period-growth-rate-numerically-unresolved", tiny["pending_reasons"]
        )
        stepped = analyze_sampled_command_matrix([[-1e-4]], comparison_matrix=[[1e-4]])
        self.assertEqual(stepped["classification"], "numerical-pending")
        self.assertEqual(
            analyze_sampled_command_matrix([[-1]])["step_check_status"],
            "step-check-not-provided",
        )

    def test_reject_bad_scalar_inputs(self):
        for period in [
            True,
            False,
            np.bool_(True),
            0,
            -1,
            np.nan,
            np.inf,
            1 + 0j,
            "0.1",
        ]:
            with self.subTest(period=period), self.assertRaises(SampledCommandError):
                sampled_command_matrices([[0]], [[1]], [[1]], period)
        for delay in [True, False, 0.0, 2, -1, np.nan, 1 + 0j]:
            with self.subTest(delay=delay), self.assertRaises(SampledCommandError):
                sampled_command_matrices([[0]], [[1]], [[1]], 1, delay_steps=delay)
        for tau in [0, -1, True, np.nan, np.inf, 1 + 0j]:
            with self.subTest(tau=tau), self.assertRaises(SampledCommandError):
                first_order_command_lag_matrix([[0]], [[1]], [[1]], tau)

    def test_reject_bad_matrices(self):
        for a in [
            [[True]],
            [[1 + 0j]],
            [[np.nan]],
            [[np.inf]],
            [[1, 2]],
            [],
            [["1"]],
            np.eye(2, dtype=complex),
        ]:
            with self.subTest(a=a), self.assertRaises(SampledCommandError):
                sampled_command_matrices(a, [[1]], [[1]], 1)
        for b, f in [([[1, 2]], [[1]]), ([[1], [2]], [[1]]), ([[1]], [[1, 2]])]:
            with self.subTest(b=b, f=f), self.assertRaises(SampledCommandError):
                sampled_command_matrices([[0]], b, f, 1)

    def test_nested_ndarray_bool_complex_object_and_extreme_tau_rejected(self):
        for row in [
            np.array([True, False]),
            np.array([1 + 0j, 2 + 0j]),
            np.array([1, 2], dtype=object),
        ]:
            nested = [row, np.array([1.0, 2.0])]
            with self.subTest(dtype=row.dtype), self.assertRaises(SampledCommandError):
                sampled_command_matrices(nested, [[1], [1]], [[1, 1]], 0.1)
        cyclic = []
        cyclic.append(cyclic)
        with self.assertRaises(SampledCommandError):
            sampled_command_matrices(cyclic, [[1]], [[1]], 0.1)
        with self.assertRaises(SampledCommandError):
            first_order_command_lag_matrix([[0]], [[1]], [[1]], 1e-320)


class AverageDQSampledCommandTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.topology, cls.params = build_average_dq_ablation_anchor_case()
        cls.model = build_average_dq_model(cls.topology, cls.params, relative_step=1e-5)
        cls.second = build_average_dq_model(
            cls.topology, cls.params, relative_step=5e-6
        )

    def test_C_sign_and_ideal_invariance(self):
        local = split_average_dq_sampled_command(self.model)
        glob = split_average_dq_sampled_command(
            self.model, holding_frame="global-synchronous-dq"
        )
        c = np.zeros((2, 14))
        c[:, 0] = J @ self.model.operating_point.state[14:]
        h = 1e-6
        actual_rotation_derivative = (_rotation(h) - _rotation(-h)) / (2 * h)
        assert_allclose(
            c[:, 0],
            actual_rotation_derivative @ self.model.operating_point.state[14:],
            atol=1e-10,
        )
        assert_allclose(glob.C, c)
        assert_allclose(glob.a0, local.a0 - local.b @ c)
        assert_allclose(glob.f, local.f + c)
        assert_allclose(
            glob.a0 + glob.b @ glob.f, local.a0 + local.b @ local.f, atol=1e-10
        )

    def test_json_summary_explicit_steps_dimensions_and_no_mutation(self):
        state = self.model.operating_point.state.copy()
        matrix = self.model.linearization.closed_state_matrix.copy()
        for hold in ["local-control-dq", "global-synchronous-dq"]:
            result = compare_average_dq_sampled_command(
                self.model,
                0.001,
                holding_frame=hold,
                delay_steps=1,
                comparison_model=self.second,
            )
            json.dumps(result, allow_nan=False)
            self.assertEqual(result["references"]["sampled_command"]["dimension"], 16)
            self.assertEqual(
                result["references"]["ideal_instantaneous"]["dimension"], 14
            )
            self.assertEqual(
                result["step_check"]["status"], "step-comparison-evaluated"
            )
            self.assertAlmostEqual(result["phase_matched_tau_s"], 0.0015)
            self.assertIn("not-evaluated", result["theorem_status"])
        assert_allclose(self.model.operating_point.state, state, atol=0, rtol=0)
        assert_allclose(
            self.model.linearization.closed_state_matrix, matrix, atol=0, rtol=0
        )
        missing = compare_average_dq_sampled_command(self.model, 0.003)
        self.assertEqual(missing["step_check"]["status"], "step-check-not-provided")
        self.assertEqual(missing["benchmark_coverage"], "not-yet-benchmark-covered")

    def test_wrong_declared_model_labels_shape_and_modulation_block_rejected(self):
        for fake in [
            SimpleNamespace(
                linearization=self.model.linearization, parameters=self.params
            ),
            object(),
        ]:
            with self.assertRaises(SampledCommandError):
                split_average_dq_sampled_command(fake)
        for labels in [
            EXPECTED_STATE_LABELS[::-1],
            EXPECTED_STATE_LABELS[:14],
            "state labels",
            None,
        ]:
            if labels is None:
                continue
            with self.assertRaises(SampledCommandError):
                split_average_dq_sampled_command(self.model, state_labels=labels)
        malformed = replace(
            self.model,
            linearization=replace(
                self.model.linearization, closed_state_matrix=np.eye(14)
            ),
        )
        with self.assertRaises(SampledCommandError):
            split_average_dq_sampled_command(malformed)
        matrix = self.model.linearization.closed_state_matrix.copy()
        matrix[14, 14] += 10
        wrong = replace(
            self.model,
            linearization=replace(self.model.linearization, closed_state_matrix=matrix),
        )
        with self.assertRaises(SampledCommandError):
            split_average_dq_sampled_command(wrong)
        for tau in [0, -1, True, np.nan, np.inf, 1 + 0j]:
            malformed = replace(
                self.model,
                parameters=self.params.model_copy(
                    update={"modulation_time_constant_s": tau}
                ),
            )
            with self.subTest(tau=tau), self.assertRaises(SampledCommandError):
                split_average_dq_sampled_command(malformed)
        state = self.model.operating_point.state.astype(complex)
        malformed = replace(
            self.model, operating_point=replace(self.model.operating_point, state=state)
        )
        with self.assertRaises(SampledCommandError):
            split_average_dq_sampled_command(malformed)

    def test_invalid_hold_and_incompatible_second_model(self):
        for period in [True, 0, -1, np.nan, np.inf, 1 + 0j]:
            with self.subTest(period=period), self.assertRaises(SampledCommandError):
                compare_average_dq_sampled_command(self.model, period)
        for hold in [True, "global", "abc", None]:
            with self.assertRaises(SampledCommandError):
                compare_average_dq_sampled_command(
                    self.model, 0.001, holding_frame=hold
                )
        with self.assertRaises(SampledCommandError):
            compare_average_dq_sampled_command(
                self.model, 0.001, comparison_model=self.model
            )
        topology, params = build_average_dq_ablation_anchor_case()
        topology.lines[0].reactance_pu += 0.01
        changed = build_average_dq_model(topology, params, relative_step=5e-6)
        with self.assertRaises(SampledCommandError):
            compare_average_dq_sampled_command(
                self.model, 0.001, comparison_model=changed
            )


if __name__ == "__main__":
    unittest.main()
