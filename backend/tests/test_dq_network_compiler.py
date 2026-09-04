from __future__ import annotations

import unittest
from copy import deepcopy

import numpy as np
from fastapi.testclient import TestClient

from backend.api.app import app
from backend.core.average_dq_model import external_line_admittance
from backend.core.dq_network_compiler import (
    DQNetworkNumericalError,
    assemble_nodal_dq_admittance,
    compile_network_to_gfm_ports,
    kron_reduce_dq,
    series_rl_dq_admittance,
)
from backend.core.reduced_order_presets import get_reduced_order_preset
from backend.domain.network_models import NetworkTopology


def base_case() -> dict:
    return (
        get_reduced_order_preset("reduced-smib-stable")
        .build_topology()
        .model_dump(mode="python")
    )


def series_three_bus_case() -> NetworkTopology:
    case = base_case()
    case["id"] = "dq-series-three-bus"
    case["buses"].append(
        {"id": "bus-mid", "name": "中间母线", "nominal_voltage_v": 690.0}
    )
    original = case["lines"][0]
    case["lines"] = [
        {
            **original,
            "id": "line-left",
            "name": "左侧线路",
            "to_bus_id": "bus-mid",
            "resistance_pu": 0.01,
            "reactance_pu": 0.12,
        },
        {
            **original,
            "id": "line-right",
            "name": "右侧线路",
            "from_bus_id": "bus-mid",
            "resistance_pu": 0.02,
            "reactance_pu": 0.18,
        },
    ]
    return NetworkTopology.model_validate(case)


class DQNetworkCompilerTest(unittest.TestCase):
    def test_single_line_block_matches_existing_average_dq_formula(self) -> None:
        topology = NetworkTopology.model_validate(base_case())
        line = topology.lines[0]
        frequencies = np.array([0.0, 0.2, 2.0, 20.0])

        actual = series_rl_dq_admittance(
            line,
            frequencies,
            topology.base_values.frequency_hz,
        )
        expected = np.asarray(
            [
                external_line_admittance(
                    line,
                    frequency,
                    topology.base_values.frequency_hz,
                )
                for frequency in frequencies
            ]
        )

        np.testing.assert_allclose(actual, expected, rtol=1.0e-13, atol=1.0e-13)

    def test_grounded_single_line_reduces_to_its_branch_admittance(self) -> None:
        topology = NetworkTopology.model_validate(base_case())
        frequencies = np.array([0.1, 1.0, 10.0])

        compiled = compile_network_to_gfm_ports(topology, frequencies)
        expected = series_rl_dq_admittance(
            topology.lines[0], frequencies, topology.base_values.frequency_hz
        )

        self.assertEqual(compiled.port_bus_ids, ("bus-gfm",))
        self.assertEqual(compiled.grounded_bus_ids, ("bus-grid",))
        self.assertEqual(compiled.eliminated_bus_ids, ())
        np.testing.assert_allclose(
            compiled.port_admittance, expected, rtol=1.0e-13, atol=1.0e-13
        )

    def test_two_series_lines_match_inverse_of_summed_impedance(self) -> None:
        topology = series_three_bus_case()
        frequencies = np.array([0.1, 3.0, 30.0])

        compiled = compile_network_to_gfm_ports(topology, frequencies)
        left = series_rl_dq_admittance(
            topology.lines[0], frequencies, topology.base_values.frequency_hz
        )
        right = series_rl_dq_admittance(
            topology.lines[1], frequencies, topology.base_values.frequency_hz
        )
        expected = np.asarray(
            [
                np.linalg.solve(
                    np.linalg.solve(left[index], np.eye(2))
                    + np.linalg.solve(right[index], np.eye(2)),
                    np.eye(2),
                )
                for index in range(frequencies.size)
            ]
        )

        self.assertEqual(compiled.eliminated_bus_ids, ("bus-mid",))
        np.testing.assert_allclose(
            compiled.port_admittance, expected, rtol=1.0e-12, atol=1.0e-12
        )

    def test_parallel_lines_add_and_inactive_line_is_ignored(self) -> None:
        case = base_case()
        first = deepcopy(case["lines"][0])
        first["id"] = "line-parallel"
        first["resistance_pu"] = 0.03
        first["reactance_pu"] = 0.4
        inactive = deepcopy(first)
        inactive["id"] = "line-inactive"
        inactive["reactance_pu"] = 0.01
        inactive["in_service"] = False
        case["lines"].extend([first, inactive])
        topology = NetworkTopology.model_validate(case)
        frequencies = np.array([0.1, 2.0])

        compiled = compile_network_to_gfm_ports(topology, frequencies)
        expected = sum(
            (
                series_rl_dq_admittance(
                    line, frequencies, topology.base_values.frequency_hz
                )
                for line in topology.lines
                if line.in_service
            ),
            np.zeros((frequencies.size, 2, 2), dtype=np.complex128),
        )

        self.assertEqual(compiled.active_line_ids, ("line-grid", "line-parallel"))
        np.testing.assert_allclose(compiled.port_admittance, expected)

    def test_bus_list_permutation_only_permutates_nodal_coordinates(self) -> None:
        topology = series_three_bus_case()
        frequencies = np.array([0.5, 5.0])
        reference = compile_network_to_gfm_ports(topology, frequencies)
        case = topology.model_dump(mode="python")
        case["buses"] = [case["buses"][2], case["buses"][0], case["buses"][1]]
        permuted = compile_network_to_gfm_ports(
            NetworkTopology.model_validate(case), frequencies
        )

        np.testing.assert_allclose(permuted.port_admittance, reference.port_admittance)

    def test_nodal_line_stamp_obeys_current_conservation_without_shunts(self) -> None:
        topology = series_three_bus_case()
        frequencies, nodal, _ = assemble_nodal_dq_admittance(topology, [1.0])
        uniform_voltage = np.tile(np.array([0.7, -0.2]), len(topology.buses))

        np.testing.assert_array_equal(frequencies, [1.0])
        np.testing.assert_allclose(nodal[0] @ uniform_voltage, 0.0, atol=1.0e-13)

    def test_singular_eliminated_block_is_reported_as_indeterminate(self) -> None:
        frequencies = np.array([1.0])
        singular = np.zeros((1, 4, 4), dtype=np.complex128)
        singular[0, :2, :2] = np.eye(2)

        with self.assertRaisesRegex(DQNetworkNumericalError, "数值待定"):
            kron_reduce_dq(
                singular,
                ("port", "internal"),
                ("port",),
                ("internal",),
                frequencies,
            )

    def test_static_load_is_rejected_instead_of_silently_ignored(self) -> None:
        case = base_case()
        case["loads"] = [
            {
                "id": "load-1",
                "name": "静态负荷",
                "bus_id": "bus-gfm",
                "load_model": "constant_power",
                "active_power_pu": 0.2,
                "reactive_power_pu": 0.05,
            }
        ]

        with self.assertRaisesRegex(ValueError, "不能忽略负荷"):
            compile_network_to_gfm_ports(NetworkTopology.model_validate(case), [1.0])


class DQNetworkCompilerApiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.client = TestClient(app)

    def test_api_preserves_order_matrix_and_claim_boundary(self) -> None:
        topology = NetworkTopology.model_validate(base_case())

        response = self.client.post(
            "/api/network/dq-admittance",
            json={
                "topology": topology.model_dump(mode="json"),
                "frequencies_hz": [0.2, 2.0, 20.0],
            },
        )

        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["network"]["port_bus_order"], ["bus-gfm"])
        self.assertEqual(body["network"]["grounded_bus_ids"], ["bus-grid"])
        self.assertEqual(body["network"]["full_nodal_shape"], [3, 4, 4])
        self.assertEqual(len(body["network"]["port_admittance"]), 3)
        self.assertEqual(len(body["network"]["singular_values"]["minimum"]), 3)
        self.assertTrue(
            all(
                maximum >= minimum > 0.0
                for maximum, minimum in zip(
                    body["network"]["singular_values"]["maximum"],
                    body["network"]["singular_values"]["minimum"],
                    strict=True,
                )
            )
        )
        self.assertIn("不评价闭环稳定性", body["model_scope"]["statement"])
        self.assertEqual(body["model_scope"]["dq_component_order"], ["d", "q"])

    def test_api_rejects_nonmonotonic_grid_and_unmodelled_load(self) -> None:
        topology = NetworkTopology.model_validate(base_case())
        nonmonotonic = self.client.post(
            "/api/network/dq-admittance",
            json={
                "topology": topology.model_dump(mode="json"),
                "frequencies_hz": [2.0, 1.0],
            },
        )
        self.assertEqual(nonmonotonic.status_code, 422)
        self.assertIn("严格递增", nonmonotonic.json()["detail"])

        case = base_case()
        case["loads"] = [
            {
                "id": "load-1",
                "name": "静态负荷",
                "bus_id": "bus-gfm",
                "load_model": "constant_power",
                "active_power_pu": 0.2,
            }
        ]
        unmodelled_load = self.client.post(
            "/api/network/dq-admittance",
            json={"topology": case, "frequencies_hz": [1.0]},
        )
        self.assertEqual(unmodelled_load.status_code, 422)
        self.assertIn("不能忽略负荷", unmodelled_load.json()["detail"])


if __name__ == "__main__":
    unittest.main()
