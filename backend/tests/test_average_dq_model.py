import math
import unittest

import numpy as np
from numpy.testing import assert_allclose

from backend.core.average_dq_model import (
    AverageDQModelError,
    J,
    build_average_dq_model,
    close_port_model_with_external_line,
    compare_with_quasisteady_reduction,
    estimate_nonlinear_angle_mode,
    external_line_admittance,
    linearize_average_dq_model,
)
from backend.core.reduced_order_model import StabilityStatus
from backend.domain.average_dq_models import default_average_dq_parameters
from backend.domain.network_models import (
    ACLine,
    BaseValues,
    Bus,
    GridFormingConverter,
    InfiniteBus,
    NetworkTopology,
    StaticLoad,
)


def average_dq_topology(
    *,
    active_power_pu: float = 0.0,
    reactive_power_pu: float = 0.0,
    grid_angle_deg: float = 0.0,
) -> NetworkTopology:
    parameters = default_average_dq_parameters()
    return NetworkTopology(
        id="average-dq-smib",
        name="平均值 dq 单机无穷大母线校核算例",
        base_values=BaseValues(
            apparent_power_va=1.0e6,
            voltage_v=690.0,
            frequency_hz=50.0,
        ),
        frame_convention_id=parameters.frame_convention_id,
        reference_bus_id="bus-grid",
        buses=[
            Bus(id="bus-gfm", name="GFM 节点", nominal_voltage_v=690.0),
            Bus(id="bus-grid", name="无限大母线节点", nominal_voltage_v=690.0),
        ],
        lines=[
            ACLine(
                id="line-grid",
                name="外部 RL 线路",
                from_bus_id="bus-gfm",
                to_bus_id="bus-grid",
                resistance_pu=0.02,
                reactance_pu=0.30,
            )
        ],
        grid_forming_converters=[
            GridFormingConverter(
                id="gfm-1",
                name="平均值 dq VSM",
                bus_id="bus-gfm",
                rated_apparent_power_va=1.0e6,
                control_mode="virtual_synchronous_machine",
                active_power_setpoint_pu=active_power_pu,
                reactive_power_setpoint_pu=reactive_power_pu,
                voltage_setpoint_pu=1.0,
                virtual_inertia_s=2.0,
                damping_coefficient_pu=60.0,
                active_power_measurement_time_constant_s=0.1,
                parameter_set_id=parameters.id,
            )
        ],
        infinite_buses=[
            InfiniteBus(
                id="grid-1",
                name="无限大母线",
                bus_id="bus-grid",
                voltage_magnitude_pu=1.0,
                voltage_angle_deg=grid_angle_deg,
            )
        ],
    )


class AverageDQModelTest(unittest.TestCase):
    def setUp(self) -> None:
        self.parameters = default_average_dq_parameters()

    def test_no_load_operating_point_matches_analytic_equilibrium(self) -> None:
        model = build_average_dq_model(average_dq_topology(), self.parameters)
        operating = model.operating_point

        self.assertEqual(model.stability, StabilityStatus.STABLE)
        assert_allclose(operating.state[[0, 1, 2, 3]], 0.0, atol=2.0e-13)
        assert_allclose(operating.state[6:8], [1.0, 0.0], atol=2.0e-13)
        assert_allclose(operating.state[8:10], 0.0, atol=2.0e-13)
        self.assertLess(operating.closed_rhs_residual_inf, 1.0e-9)
        self.assertLess(operating.device_rhs_residual_inf, 1.0e-9)
        self.assertLess(abs(operating.active_power_balance_residual_pu), 1.0e-12)

    def test_loaded_equilibrium_respects_setpoints_and_power_balance(self) -> None:
        model = build_average_dq_model(
            average_dq_topology(active_power_pu=0.5, reactive_power_pu=0.1),
            self.parameters,
        )
        operating = model.operating_point

        assert_allclose(operating.state[2], 0.5, atol=1.0e-10)
        self.assertLess(np.linalg.norm(operating.algebraic_residual, ord=np.inf), 1.0e-10)
        self.assertLess(abs(operating.active_power_balance_residual_pu), 1.0e-8)
        self.assertLess(
            operating.grid_current_magnitude_pu,
            self.parameters.diagnostic_current_limit_pu,
        )

    def test_global_rotation_preserves_poles_power_and_rotates_admittance(self) -> None:
        base = build_average_dq_model(
            average_dq_topology(active_power_pu=0.5, reactive_power_pu=0.1),
            self.parameters,
        )
        angle_deg = 17.0
        rotated = build_average_dq_model(
            average_dq_topology(
                active_power_pu=0.5,
                reactive_power_pu=0.1,
                grid_angle_deg=angle_deg,
            ),
            self.parameters,
        )
        angle = math.radians(angle_deg)
        rotation = np.array(
            [[math.cos(angle), -math.sin(angle)], [math.sin(angle), math.cos(angle)]]
        )

        assert_allclose(base.poles_per_s, rotated.poles_per_s, rtol=2.0e-8, atol=2.0e-8)
        self.assertAlmostEqual(
            rotated.operating_point.state[0] - base.operating_point.state[0],
            angle,
            places=10,
        )
        assert_allclose(rotated.operating_point.state[2:4], base.operating_point.state[2:4], atol=1.0e-10)
        base_admittance = base.port_admittance([0.2, 2.0, 20.0])
        rotated_admittance = rotated.port_admittance([0.2, 2.0, 20.0])
        for base_value, rotated_value in zip(base_admittance, rotated_admittance):
            assert_allclose(
                rotated_value,
                rotation @ base_value @ rotation.T,
                rtol=2.0e-7,
                atol=2.0e-8,
            )

    def test_line_admittance_matches_explicit_rl_matrix_inverse(self) -> None:
        line = average_dq_topology().lines[0]
        for frequency_hz in (0.0, 0.5, 10.0, 100.0):
            calculated = external_line_admittance(line, frequency_hz, 50.0)
            s = 1j * 2.0 * math.pi * frequency_hz
            expected_impedance = (
                line.resistance_pu
                + line.reactance_pu / (2.0 * math.pi * 50.0) * s
            ) * np.eye(2) + line.reactance_pu * J
            assert_allclose(calculated @ expected_impedance, np.eye(2), atol=2.0e-13)

    def test_port_interconnection_reassembles_direct_closed_state_matrix(self) -> None:
        model = build_average_dq_model(
            average_dq_topology(active_power_pu=0.5, reactive_power_pu=0.1),
            self.parameters,
        )
        reconstructed = close_port_model_with_external_line(
            model.linearization,
            model.line,
            model.topology.base_values.frequency_hz,
        )

        assert_allclose(
            reconstructed,
            model.linearization.closed_state_matrix,
            rtol=2.0e-8,
            atol=2.0e-7,
        )
        assert_allclose(
            np.sort_complex(np.linalg.eigvals(reconstructed)),
            model.poles_per_s,
            rtol=2.0e-7,
            atol=2.0e-6,
        )

    def test_jacobian_converges_when_step_is_halved(self) -> None:
        model = build_average_dq_model(
            average_dq_topology(active_power_pu=0.5, reactive_power_pu=0.1),
            self.parameters,
            relative_step=1.0e-3,
        )
        linear_half = linearize_average_dq_model(
            model.topology,
            model.parameters,
            model.converter,
            model.line,
            model.operating_point,
            relative_step=5.0e-4,
        )
        linear_quarter = linearize_average_dq_model(
            model.topology,
            model.parameters,
            model.converter,
            model.line,
            model.operating_point,
            relative_step=2.5e-4,
        )
        first_difference = np.linalg.norm(
            model.linearization.closed_state_matrix
            - linear_half.closed_state_matrix,
            ord=np.inf,
        )
        second_difference = np.linalg.norm(
            linear_half.closed_state_matrix
            - linear_quarter.closed_state_matrix,
            ord=np.inf,
        )
        matrix_scale = np.linalg.norm(
            linear_quarter.closed_state_matrix, ord=np.inf
        )
        self.assertLess(second_difference / matrix_scale, 2.0e-9)
        self.assertLess(second_difference, 0.3 * first_difference)

    def test_nonlinear_small_signal_response_matches_linearization(self) -> None:
        model = build_average_dq_model(
            average_dq_topology(active_power_pu=0.5, reactive_power_pu=0.1),
            self.parameters,
        )
        initial = model.operating_point.state.copy()
        initial[0] += 1.0e-4
        response = model.nonlinear_linear_response(
            np.linspace(0.0, 0.5, 251),
            initial_state=initial,
            relative_tolerance=1.0e-11,
            absolute_tolerance=1.0e-13,
        )
        error = np.max(np.abs(response.nonlinear_states - response.linear_states))
        perturbation = np.max(
            np.abs(response.linear_states - model.operating_point.state)
        )
        self.assertLess(error / perturbation, 1.0e-4)

    def test_damping_change_crosses_a_reproducible_stability_boundary(self) -> None:
        low_damping_topology = average_dq_topology(
            active_power_pu=0.5, reactive_power_pu=0.1
        )
        low_damping_topology.grid_forming_converters[
            0
        ].damping_coefficient_pu = 20.0
        high_damping_topology = average_dq_topology(
            active_power_pu=0.5, reactive_power_pu=0.1
        )
        high_damping_topology.grid_forming_converters[
            0
        ].damping_coefficient_pu = 40.0

        low = build_average_dq_model(low_damping_topology, self.parameters)
        high = build_average_dq_model(high_damping_topology, self.parameters)

        self.assertEqual(low.stability, StabilityStatus.UNSTABLE)
        self.assertEqual(high.stability, StabilityStatus.STABLE)
        self.assertGreater(np.max(low.poles_per_s.real), 1.0)
        self.assertLess(np.max(high.poles_per_s.real), -1.0)

    def test_nonlinear_free_decay_identifies_dominant_pole(self) -> None:
        model = build_average_dq_model(
            average_dq_topology(active_power_pu=0.5, reactive_power_pu=0.1),
            self.parameters,
        )
        initial = model.operating_point.state.copy()
        initial[0] += 1.0e-3
        response = model.nonlinear_linear_response(
            np.linspace(0.0, 3.0, 3001),
            initial_state=initial,
            relative_tolerance=1.0e-10,
            absolute_tolerance=1.0e-12,
        )
        estimate = estimate_nonlinear_angle_mode(
            response, model.operating_point.state[0]
        )
        dominant = max(model.poles_per_s, key=lambda pole: pole.real)
        expected_frequency = abs(dominant.imag) / (2.0 * math.pi)
        expected_decay = -dominant.real

        self.assertGreaterEqual(estimate.peak_count, 4)
        self.assertLess(
            abs(estimate.oscillation_frequency_hz - expected_frequency)
            / expected_frequency,
            0.02,
        )
        self.assertLess(
            abs(estimate.decay_rate_per_s - expected_decay) / expected_decay,
            0.05,
        )

    def test_working_point_matched_reduction_recovers_dominant_mode(self) -> None:
        model = build_average_dq_model(
            average_dq_topology(active_power_pu=0.5, reactive_power_pu=0.1),
            self.parameters,
        )
        comparison = compare_with_quasisteady_reduction(model)

        self.assertGreater(comparison.synchronizing_stiffness_pu_per_rad, 0.0)
        self.assertLess(comparison.oscillation_frequency_relative_error, 0.05)
        self.assertLess(comparison.decay_rate_relative_error, 0.05)
        self.assertEqual(comparison.reduced_state_matrix.shape, (3, 3))
        self.assertEqual(comparison.reduced_poles_per_s.shape, (3,))

    def test_scope_rejects_static_load_and_parameter_mismatch(self) -> None:
        topology = average_dq_topology()
        topology.loads.append(
            StaticLoad(
                id="load-1",
                name="unsupported load",
                bus_id="bus-gfm",
                active_power_pu=0.1,
            )
        )
        with self.assertRaisesRegex(AverageDQModelError, "不支持静态负荷"):
            build_average_dq_model(topology, self.parameters)

        topology = average_dq_topology()
        topology.grid_forming_converters[0].parameter_set_id = "wrong-set"
        with self.assertRaisesRegex(AverageDQModelError, "parameter_set_id"):
            build_average_dq_model(topology, self.parameters)


if __name__ == "__main__":
    unittest.main()
