from __future__ import annotations

from math import pi, sqrt
import unittest

import numpy as np

from backend.core.reduced_order_model import (
    ReducedOrderModelError,
    StabilityStatus,
    build_reduced_order_model,
)
from backend.domain.network_models import NetworkTopology


INERTIA_S = 2.0
MEASUREMENT_TIME_S = 0.1
LINE_REACTANCE_PU = 0.2
SYNCHRONOUS_STIFFNESS = 1.0 / LINE_REACTANCE_PU


def single_machine_topology(
    damping: float,
    *,
    control_mode: str = "virtual_synchronous_machine",
    include_infinite_bus: bool = True,
    include_interior_bus: bool = False,
) -> NetworkTopology:
    if control_mode == "virtual_synchronous_machine":
        controller_parameters = {
            "virtual_inertia_s": INERTIA_S,
            "damping_coefficient_pu": damping,
            "active_power_measurement_time_constant_s": MEASUREMENT_TIME_S,
        }
    else:
        controller_parameters = {
            "active_power_frequency_droop_pu": 0.05,
            "reactive_power_voltage_droop_pu": 0.05,
        }

    buses = [
        {
            "id": "bus-gfm",
            "name": "VSM 节点",
            "nominal_voltage_v": 690.0,
        },
        {
            "id": "bus-grid",
            "name": "电网侧节点",
            "nominal_voltage_v": 690.0,
        },
    ]
    if include_interior_bus:
        buses.insert(
            1,
            {
                "id": "bus-mid",
                "name": "无动态中间节点",
                "nominal_voltage_v": 690.0,
            },
        )
        lines = [
            {
                "id": "line-left",
                "name": "左侧线路",
                "from_bus_id": "bus-gfm",
                "to_bus_id": "bus-mid",
                "resistance_pu": 0.02,
                "reactance_pu": 0.2,
            },
            {
                "id": "line-right",
                "name": "右侧线路",
                "from_bus_id": "bus-mid",
                "to_bus_id": "bus-grid",
                "resistance_pu": 0.03,
                "reactance_pu": 0.3,
            },
        ]
    else:
        lines = [
            {
                "id": "line-grid",
                "name": "并网线路",
                "from_bus_id": "bus-gfm",
                "to_bus_id": "bus-grid",
                "resistance_pu": 0.02,
                "reactance_pu": LINE_REACTANCE_PU,
            }
        ]

    return NetworkTopology.model_validate(
        {
            "id": f"single-machine-d-{damping:.12g}",
            "name": "单机—无限大母线低频降阶算例",
            "base_values": {
                "apparent_power_va": 1.0e6,
                "voltage_v": 690.0,
                "frequency_hz": 50.0,
            },
            "frame_convention_id": "global-synchronous-angle-v1",
            "reference_bus_id": "bus-grid" if include_infinite_bus else "bus-gfm",
            "buses": buses,
            "lines": lines,
            "grid_forming_converters": [
                {
                    "id": "gfm-1",
                    "name": "构网型变流器",
                    "bus_id": "bus-gfm",
                    "rated_apparent_power_va": 1.0e6,
                    "control_mode": control_mode,
                    **controller_parameters,
                }
            ],
            "infinite_buses": (
                [
                    {
                        "id": "grid-1",
                        "name": "无限大母线",
                        "bus_id": "bus-grid",
                    }
                ]
                if include_infinite_bus
                else []
            ),
            "loads": (
                [
                    {
                        "id": "load-mid",
                        "name": "中间节点恒功率负荷",
                        "bus_id": "bus-mid",
                        "active_power_pu": 0.1,
                        "reactive_power_pu": 0.02,
                    }
                ]
                if include_interior_bus
                else []
            ),
        }
    )


def critical_damping() -> float:
    # Routh--Hurwitz boundary for
    # M*T*s^3 + (M + D*T)*s^2 + D*s + omega_b*K = 0.
    omega_base = 2.0 * pi * 50.0
    return (
        -INERTIA_S
        + sqrt(
            INERTIA_S**2
            + 4.0
            * INERTIA_S
            * MEASUREMENT_TIME_S**2
            * omega_base
            * SYNCHRONOUS_STIFFNESS
        )
    ) / (2.0 * MEASUREMENT_TIME_S)


class ReducedOrderModelTest(unittest.TestCase):
    def test_kron_reduction_matches_two_series_reactances(self) -> None:
        topology = single_machine_topology(
            0.8,
            include_interior_bus=True,
        )

        model = build_reduced_order_model(topology)

        np.testing.assert_allclose(
            model.synchronous_stiffness_matrix,
            [[1.0 / (0.2 + 0.3)]],
            rtol=1.0e-12,
            atol=1.0e-12,
        )

    def test_stable_single_machine_poles_match_analytic_cubic(self) -> None:
        damping = 60.0
        omega_base = 2.0 * pi * 50.0
        model = build_reduced_order_model(single_machine_topology(damping))
        expected_poles = np.roots(
            [
                INERTIA_S * MEASUREMENT_TIME_S,
                INERTIA_S + damping * MEASUREMENT_TIME_S,
                damping,
                omega_base * SYNCHRONOUS_STIFFNESS,
            ]
        )

        np.testing.assert_allclose(
            model.state_matrix,
            [
                [0.0, omega_base, 0.0],
                [0.0, -damping / INERTIA_S, -1.0 / INERTIA_S],
                [
                    SYNCHRONOUS_STIFFNESS / MEASUREMENT_TIME_S,
                    0.0,
                    -1.0 / MEASUREMENT_TIME_S,
                ],
            ],
            rtol=0.0,
            atol=1.0e-14,
        )
        np.testing.assert_allclose(
            model.poles_per_s,
            np.sort_complex(expected_poles),
            rtol=1.0e-11,
            atol=1.0e-11,
        )
        np.testing.assert_allclose(
            model.poles_hz,
            model.poles_per_s / (2.0 * pi),
            rtol=0.0,
            atol=1.0e-15,
        )
        self.assertEqual(model.stability, StabilityStatus.STABLE)
        self.assertLess(model.dominant_mode.eigenvalue_per_s.real, 0.0)

    def test_analytic_critical_damping_has_marginal_oscillatory_pair(self) -> None:
        damping = critical_damping()
        model = build_reduced_order_model(single_machine_topology(damping))
        omega_base = 2.0 * pi * 50.0
        expected_frequency_hz = sqrt(
            omega_base * SYNCHRONOUS_STIFFNESS
            / (INERTIA_S + damping * MEASUREMENT_TIME_S)
        ) / (2.0 * pi)

        self.assertEqual(model.stability, StabilityStatus.MARGINAL)
        self.assertAlmostEqual(
            model.dominant_mode.eigenvalue_per_s.real,
            0.0,
            delta=1.0e-10,
        )
        self.assertAlmostEqual(
            model.dominant_mode.oscillation_frequency_hz,
            expected_frequency_hz,
            delta=1.0e-10,
        )

    def test_low_damping_case_is_unstable(self) -> None:
        model = build_reduced_order_model(single_machine_topology(0.05))

        self.assertEqual(model.stability, StabilityStatus.UNSTABLE)
        self.assertGreater(model.dominant_mode.eigenvalue_per_s.real, 0.0)
        self.assertGreater(model.dominant_mode.oscillation_frequency_hz, 0.0)

    def test_time_response_frequency_matches_dominant_pole(self) -> None:
        model = build_reduced_order_model(
            single_machine_topology(critical_damping())
        )
        times = np.linspace(0.0, 80.0, 4001)

        response = model.linear_time_response(
            times,
            initial_state=[1.0e-3, 0.0, 0.0],
        )

        retained = response.states[times >= 20.0, 0]
        retained = retained - np.mean(retained)
        sample_interval = times[1] - times[0]
        frequencies = np.fft.rfftfreq(retained.size, d=sample_interval)
        spectrum = np.abs(np.fft.rfft(retained))
        peak_index = int(np.argmax(spectrum[1:]) + 1)
        self.assertAlmostEqual(
            frequencies[peak_index],
            model.dominant_mode.oscillation_frequency_hz,
            delta=0.01,
        )

    def test_pure_island_is_rejected_with_scope_explanation(self) -> None:
        topology = single_machine_topology(
            60.0,
            include_infinite_bus=False,
        )

        with self.assertRaisesRegex(
            ReducedOrderModelError,
            "纯孤岛系统含公共旋转模态",
        ):
            build_reduced_order_model(topology)

    def test_reference_bus_must_be_grounded_infinite_bus(self) -> None:
        topology = single_machine_topology(60.0)
        topology.reference_bus_id = "bus-gfm"

        with self.assertRaisesRegex(
            ReducedOrderModelError,
            "reference_bus_id 指向无限大母线所在节点",
        ):
            build_reduced_order_model(topology)

    def test_unsupported_droop_controller_is_rejected(self) -> None:
        topology = single_machine_topology(
            60.0,
            control_mode="droop",
        )

        with self.assertRaisesRegex(
            ReducedOrderModelError,
            "仅支持 virtual_synchronous_machine",
        ):
            build_reduced_order_model(topology)

    def test_assumptions_explicitly_exclude_unmodelled_dynamics(self) -> None:
        model = build_reduced_order_model(single_machine_topology(0.8))
        assumptions = "".join(model.assumptions)

        self.assertIn("线路电阻", assumptions)
        self.assertIn("无功—电压耦合", assumptions)
        self.assertIn("变流器内环", assumptions)

    def test_time_response_rejects_nonmonotonic_samples(self) -> None:
        model = build_reduced_order_model(single_machine_topology(0.8))

        with self.assertRaisesRegex(ReducedOrderModelError, "单调不减"):
            model.linear_time_response([0.0, 1.0, 0.5])


if __name__ == "__main__":
    unittest.main()
