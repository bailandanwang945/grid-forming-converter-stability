from __future__ import annotations

import math
import unittest

from backend.core.average_dq_boundary import (
    AverageDQBoundaryError,
    BoundaryTrial,
    _solve_scalar_boundary,
    run_average_dq_boundary_study,
)
from backend.core.average_dq_presets import (
    build_average_dq_ablation_anchor_case,
)


def _trial(factor: float, value: float | None) -> BoundaryTrial:
    valid = value is not None
    pole = complex(value, 1.0) if valid else None
    return BoundaryTrial(
        factor_value=factor,
        calculation_status="valid" if valid else "numerical-pending",
        reason="accepted" if valid else "synthetic-pending",
        stability="stable" if valid and value < 0.0 else "unstable",
        spectral_abscissa_per_s=value,
        rightmost_pole_per_s=pole,
        extra_mode_per_s=pole,
        synchronous_mode_per_s=complex(-1.0, 2.0) if valid else None,
        extra_mode_status="matched" if valid else "pending",
        synchronous_mode_status="matched" if valid else "pending",
        extra_mode_is_rightmost=valid,
        extra_match=None,
        algebraic_residual_inf=0.0 if valid else None,
        closed_rhs_residual_inf=0.0 if valid else None,
        active_power_balance_abs_pu=0.0 if valid else None,
    )


class _SyntheticEvaluator:
    def __init__(self, function):  # type: ignore[no-untyped-def]
        self.function = function
        self.cache: dict[float, BoundaryTrial] = {}

    def evaluate(self, factor: float) -> BoundaryTrial:
        if factor not in self.cache:
            self.cache[factor] = _trial(factor, self.function(factor))
        return self.cache[factor]


class AverageDQBoundaryStudyTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        topology, parameters = build_average_dq_ablation_anchor_case()
        cls.topology_before = topology.model_dump(mode="json")
        cls.parameters_before = parameters.model_dump(mode="json")
        cls.study = run_average_dq_boundary_study(topology, parameters)
        cls.topology_after = topology.model_dump(mode="json")
        cls.parameters_after = parameters.model_dump(mode="json")

    def test_four_frozen_paths_converge_to_reproducible_boundaries(self) -> None:
        expected = {
            "voltage-pi-boundary": 1.629746,
            "current-pi-boundary": 1.601645,
            "converter-side-reactance-boundary": 0.693169,
            "grid-side-reactance-boundary": 1.994560,
        }
        self.assertEqual(len(self.study.paths), 4)
        for path in self.study.paths:
            with self.subTest(path=path.definition.path_id):
                extra = path.extra_mode_boundary
                overall = path.overall_stability_boundary
                self.assertEqual(extra.status, "converged")
                self.assertEqual(overall.status, "converged")
                self.assertIsNotNone(extra.factor_value)
                self.assertAlmostEqual(
                    extra.factor_value,
                    expected[path.definition.path_id],
                    delta=2.0e-5,
                )
                self.assertEqual(extra.factor_value, overall.factor_value)
                self.assertTrue(path.boundaries_agree)
                self.assertEqual(path.relative_boundary_difference, 0.0)

    def test_trials_preserve_sign_brackets_tracking_and_physical_residuals(self) -> None:
        for path in self.study.paths:
            with self.subTest(path=path.definition.path_id):
                self.assertGreaterEqual(len(path.trials), 10)
                endpoint_values = {
                    trial.factor_value: trial for trial in path.trials
                }
                first = endpoint_values[min(1.0, path.definition.endpoint_factor)]
                second = endpoint_values[max(1.0, path.definition.endpoint_factor)]
                self.assertLess(
                    first.spectral_abscissa_per_s * second.spectral_abscissa_per_s,
                    0.0,
                )
                for trial in path.trials:
                    self.assertEqual(trial.calculation_status, "valid")
                    self.assertEqual(trial.extra_mode_status, "matched")
                    self.assertEqual(trial.synchronous_mode_status, "matched")
                    self.assertLess(trial.algebraic_residual_inf, 1.0e-9)
                    self.assertLess(trial.closed_rhs_residual_inf, 1.0e-9)
                    self.assertLess(trial.active_power_balance_abs_pu, 1.0e-9)

    def test_mode_handoff_is_reported_separately_from_boundary_identity(self) -> None:
        handoff = {
            path.definition.path_id: path.mode_handoff_observed
            for path in self.study.paths
        }
        self.assertEqual(
            handoff,
            {
                "voltage-pi-boundary": True,
                "current-pi-boundary": True,
                "converter-side-reactance-boundary": True,
                "grid-side-reactance-boundary": False,
            },
        )

    def test_inputs_are_not_mutated_and_scope_is_explicit(self) -> None:
        self.assertEqual(self.topology_before, self.topology_after)
        self.assertEqual(self.parameters_before, self.parameters_after)
        self.assertIn("四条冻结单因素路径", self.study.interpretation_boundary)
        self.assertIn("不证明唯一因果", self.study.interpretation_boundary)

    def test_invalid_numerical_contract_is_rejected_before_model_build(self) -> None:
        topology, parameters = build_average_dq_ablation_anchor_case()
        for keyword, value in (
            ("factor_relative_tolerance", 0.0),
            ("real_part_tolerance_per_s", float("nan")),
            ("maximum_iterations", 0),
        ):
            with self.subTest(keyword=keyword):
                with self.assertRaises(AverageDQBoundaryError):
                    run_average_dq_boundary_study(
                        topology,
                        parameters,
                        **{keyword: value},
                    )


class ScalarBoundarySolverTest(unittest.TestCase):
    def test_logarithmic_bisection_finds_a_bracketed_root(self) -> None:
        evaluator = _SyntheticEvaluator(lambda factor: math.log(factor / 1.5))
        result = _solve_scalar_boundary(
            evaluator,
            "spectral-abscissa",
            1.0,
            2.0,
            factor_relative_tolerance=1.0e-7,
            real_part_tolerance_per_s=1.0e-9,
            maximum_iterations=40,
        )
        self.assertEqual(result.status, "converged")
        self.assertAlmostEqual(result.factor_value, 1.5, delta=2.0e-7)

    def test_same_sign_endpoints_remain_unbracketed(self) -> None:
        evaluator = _SyntheticEvaluator(lambda factor: factor + 1.0)
        result = _solve_scalar_boundary(
            evaluator,
            "spectral-abscissa",
            1.0,
            2.0,
            factor_relative_tolerance=1.0e-5,
            real_part_tolerance_per_s=1.0e-5,
            maximum_iterations=20,
        )
        self.assertEqual(result.status, "unbracketed")
        self.assertIsNone(result.factor_value)

    def test_pending_midpoint_is_not_forced_through_solver(self) -> None:
        midpoint = math.sqrt(2.0)

        def function(factor: float) -> float | None:
            if abs(factor - midpoint) < 1.0e-12:
                return None
            return factor - midpoint

        result = _solve_scalar_boundary(
            _SyntheticEvaluator(function),
            "extra-mode-real-part",
            1.0,
            2.0,
            factor_relative_tolerance=1.0e-5,
            real_part_tolerance_per_s=1.0e-5,
            maximum_iterations=20,
        )
        self.assertEqual(result.status, "pending")
        self.assertIsNone(result.factor_value)


if __name__ == "__main__":
    unittest.main()
