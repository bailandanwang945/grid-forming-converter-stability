from __future__ import annotations

import unittest

from fastapi.testclient import TestClient

from backend.api.app import app
from backend.core.reduced_order_contingency import evaluate_line_outages
from backend.core.reduced_order_presets import get_reduced_order_preset
from backend.domain.network_models import NetworkTopology


def meshed_three_bus_topology() -> NetworkTopology:
    case = get_reduced_order_preset("reduced-smib-stable").build_topology().model_dump(
        mode="python"
    )
    case["id"] = "meshed-three-bus"
    case["name"] = "三母线环网 N-1 校核算例"
    case["buses"].append(
        {"id": "bus-mid", "name": "中间母线", "nominal_voltage_v": 690.0}
    )
    case["lines"] = [
        {
            "id": "line-direct",
            "name": "直联线路",
            "from_bus_id": "bus-gfm",
            "to_bus_id": "bus-grid",
            "resistance_pu": 0.02,
            "reactance_pu": 0.4,
        },
        {
            "id": "line-left",
            "name": "左侧线路",
            "from_bus_id": "bus-gfm",
            "to_bus_id": "bus-mid",
            "resistance_pu": 0.01,
            "reactance_pu": 0.2,
        },
        {
            "id": "line-right",
            "name": "右侧线路",
            "from_bus_id": "bus-mid",
            "to_bus_id": "bus-grid",
            "resistance_pu": 0.01,
            "reactance_pu": 0.2,
        },
    ]
    return NetworkTopology.model_validate(case)


class ReducedOrderContingencyTest(unittest.TestCase):
    def test_radial_line_outage_is_reported_as_islanding(self) -> None:
        topology = get_reduced_order_preset("reduced-smib-stable").build_topology()

        study = evaluate_line_outages(topology)

        self.assertEqual(study.counts["total"], 1)
        self.assertEqual(study.counts["islanding"], 1)
        self.assertEqual(study.cases[0].outcome, "islanding")
        self.assertEqual(study.cases[0].disconnected_bus_ids, ("bus-gfm",))
        self.assertIsNone(study.cases[0].stability)

    def test_meshed_network_rebuilds_every_connected_outage_case(self) -> None:
        topology = meshed_three_bus_topology()
        original = topology.model_dump(mode="json")

        study = evaluate_line_outages(topology)

        self.assertEqual(study.counts["total"], 3)
        self.assertEqual(study.counts["analyzed"], 3)
        self.assertEqual(study.counts["islanding"], 0)
        self.assertTrue(all(case.outcome == "analyzed" for case in study.cases))
        self.assertTrue(all(case.stability is not None for case in study.cases))
        self.assertTrue(
            all(case.spectral_abscissa_shift_per_s is not None for case in study.cases)
        )
        self.assertEqual(topology.model_dump(mode="json"), original)

    def test_out_of_service_lines_are_not_retested(self) -> None:
        case = meshed_three_bus_topology().model_dump(mode="python")
        case["lines"][0]["in_service"] = False
        topology = NetworkTopology.model_validate(case)

        study = evaluate_line_outages(topology)

        self.assertEqual(study.counts["total"], 2)
        self.assertNotIn("line-direct", {item.line_id for item in study.cases})


class ReducedOrderContingencyApiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.client = TestClient(app)

    def test_api_reports_islanding_without_claiming_security_assessment(self) -> None:
        topology = get_reduced_order_preset("reduced-smib-stable").build_topology()

        response = self.client.post(
            "/api/reduced-order/n-minus-one",
            json={"topology": topology.model_dump(mode="json")},
        )

        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["study"]["counts"]["islanding"], 1)
        self.assertEqual(body["study"]["cases"][0]["outcome"], "islanding")
        self.assertIsNone(body["study"]["cases"][0]["stability"])
        self.assertIn("不是交流潮流 N−1 安全校核", body["model_scope"]["statement"])
        self.assertIn("不评价热稳", body["model_scope"]["statement"])
        self.assertFalse(body["provenance"]["input_topology_mutated"])

    def test_api_rebuilds_all_non_islanding_outages(self) -> None:
        response = self.client.post(
            "/api/reduced-order/n-minus-one",
            json={"topology": meshed_three_bus_topology().model_dump(mode="json")},
        )

        self.assertEqual(response.status_code, 200, response.text)
        study = response.json()["study"]
        self.assertEqual(study["counts"]["analyzed"], 3)
        self.assertEqual(study["counts"]["islanding"], 0)
        self.assertTrue(
            all(case["spectral_abscissa_shift_per_s"] is not None for case in study["cases"])
        )


if __name__ == "__main__":
    unittest.main()
