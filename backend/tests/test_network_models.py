from __future__ import annotations

from copy import deepcopy
import unittest

from pydantic import ValidationError

from backend.domain.network_models import NetworkTopology


def valid_two_bus_case() -> dict:
    return {
        "id": "smib-case",
        "name": "单机构网型变流器—无限大母线算例",
        "base_values": {
            "apparent_power_va": 1.0e6,
            "voltage_v": 690.0,
            "frequency_hz": 50.0,
        },
        "frame_convention_id": "global-synchronous-dq-v1",
        "reference_bus_id": "bus-grid",
        "buses": [
            {
                "id": "bus-gfm",
                "name": "变流器并网节点",
                "nominal_voltage_v": 690.0,
            },
            {
                "id": "bus-grid",
                "name": "无限大母线节点",
                "nominal_voltage_v": 690.0,
            },
        ],
        "lines": [
            {
                "id": "line-1",
                "name": "并网线路",
                "from_bus_id": "bus-gfm",
                "to_bus_id": "bus-grid",
                "resistance_pu": 0.02,
                "reactance_pu": 0.20,
                "thermal_limit_pu": 1.2,
            }
        ],
        "grid_forming_converters": [
            {
                "id": "gfm-1",
                "name": "VSM 构网型变流器",
                "bus_id": "bus-gfm",
                "rated_apparent_power_va": 1.0e6,
                "control_mode": "virtual_synchronous_machine",
                "active_power_setpoint_pu": 0.5,
                "reactive_power_setpoint_pu": 0.0,
                "voltage_setpoint_pu": 1.0,
                "virtual_inertia_s": 2.0,
                "damping_coefficient_pu": 0.5,
                "active_power_measurement_time_constant_s": 0.1,
            }
        ],
        "infinite_buses": [
            {
                "id": "grid-1",
                "name": "无限大电网",
                "bus_id": "bus-grid",
                "voltage_magnitude_pu": 1.0,
                "voltage_angle_deg": 0.0,
            }
        ],
        "loads": [
            {
                "id": "load-1",
                "name": "本地负荷",
                "bus_id": "bus-gfm",
                "load_model": "constant_power",
                "active_power_pu": 0.2,
                "reactive_power_pu": 0.05,
            }
        ],
    }


class NetworkTopologyTest(unittest.TestCase):
    def validation_message(self, case: dict) -> str:
        with self.assertRaises(ValidationError) as raised:
            NetworkTopology.model_validate(case)
        return str(raised.exception)

    def test_valid_two_bus_case_round_trips_as_json(self) -> None:
        topology = NetworkTopology.model_validate(valid_two_bus_case())

        restored = NetworkTopology.model_validate_json(topology.model_dump_json())

        self.assertEqual(restored, topology)
        self.assertEqual(restored.reference_bus_id, "bus-grid")
        self.assertEqual(
            restored.grid_forming_converters[0].virtual_inertia_s, 2.0
        )
        self.assertEqual(
            restored.grid_forming_converters[
                0
            ].active_power_measurement_time_constant_s,
            0.1,
        )

    def test_rejects_duplicate_ids_across_entity_types(self) -> None:
        case = valid_two_bus_case()
        case["loads"][0]["id"] = "line-1"

        message = self.validation_message(case)

        self.assertIn("网络实体 ID 必须全局唯一", message)
        self.assertIn("line-1", message)

    def test_rejects_unknown_line_endpoint(self) -> None:
        case = valid_two_bus_case()
        case["lines"][0]["to_bus_id"] = "bus-missing"

        message = self.validation_message(case)

        self.assertIn("末端节点 'bus-missing' 不存在", message)

    def test_rejects_unknown_attached_element_bus(self) -> None:
        case = valid_two_bus_case()
        case["loads"][0]["bus_id"] = "bus-missing"

        message = self.validation_message(case)

        self.assertIn(
            "静态负荷 'load-1' 所连接的节点 'bus-missing' 不存在", message
        )

    def test_requires_existing_reference_bus(self) -> None:
        case = valid_two_bus_case()
        case["reference_bus_id"] = "bus-missing"

        message = self.validation_message(case)

        self.assertIn("参考节点 'bus-missing' 不存在", message)

    def test_rejects_disconnected_network(self) -> None:
        case = valid_two_bus_case()
        case["buses"].append(
            {
                "id": "bus-island",
                "name": "孤立节点",
                "nominal_voltage_v": 690.0,
            }
        )

        message = self.validation_message(case)

        self.assertIn("网络拓扑不连通", message)
        self.assertIn("bus-island", message)

    def test_rejects_line_used_between_different_voltage_levels(self) -> None:
        case = valid_two_bus_case()
        case["buses"][1]["nominal_voltage_v"] = 10_000.0

        message = self.validation_message(case)

        self.assertIn("当前契约不以线路替代变压器模型", message)

    def test_rejects_self_loop_line(self) -> None:
        case = valid_two_bus_case()
        case["lines"][0]["to_bus_id"] = "bus-gfm"

        message = self.validation_message(case)

        self.assertIn("首、末端节点不能相同", message)

    def test_requires_a_grid_forming_voltage_source(self) -> None:
        case = valid_two_bus_case()
        case["grid_forming_converters"] = []
        case["infinite_buses"] = []

        message = self.validation_message(case)

        self.assertIn("至少需要一个构网型变流器或无限大母线", message)

    def test_requires_parameters_for_selected_gfm_controller(self) -> None:
        case = valid_two_bus_case()
        case["grid_forming_converters"][0].pop("virtual_inertia_s")

        message = self.validation_message(case)

        self.assertIn("虚拟同步机控制必须给出 virtual_inertia_s", message)

    def test_requires_active_power_measurement_time_constant_for_vsm(self) -> None:
        case = valid_two_bus_case()
        case["grid_forming_converters"][0].pop(
            "active_power_measurement_time_constant_s"
        )

        message = self.validation_message(case)

        self.assertIn("active_power_measurement_time_constant_s", message)

    def test_rejects_out_of_range_parameters(self) -> None:
        cases = [
            (("base_values", "frequency_hz"), 0.0, "frequency_hz"),
            (("lines", 0, "resistance_pu"), -0.01, "resistance_pu"),
            (("loads", 0, "active_power_pu"), -0.1, "active_power_pu"),
            (
                ("infinite_buses", 0, "voltage_magnitude_pu"),
                2.0,
                "voltage_magnitude_pu",
            ),
        ]
        for path, value, expected_field in cases:
            with self.subTest(field=expected_field):
                case = deepcopy(valid_two_bus_case())
                target = case
                for segment in path[:-1]:
                    target = target[segment]
                target[path[-1]] = value

                message = self.validation_message(case)

                self.assertIn(expected_field, message)

    def test_allows_an_islanded_single_bus_gfm_case(self) -> None:
        case = valid_two_bus_case()
        case["reference_bus_id"] = "bus-gfm"
        case["buses"] = [case["buses"][0]]
        case["lines"] = []
        case["infinite_buses"] = []

        topology = NetworkTopology.model_validate(case)

        self.assertEqual(len(topology.buses), 1)
        self.assertEqual(topology.infinite_buses, [])

    def test_rejects_unknown_fields_in_external_input(self) -> None:
        case = valid_two_bus_case()
        case["lines"][0]["resistence_pu"] = 0.02

        message = self.validation_message(case)

        self.assertIn("resistence_pu", message)
        self.assertIn("Extra inputs are not permitted", message)


if __name__ == "__main__":
    unittest.main()
