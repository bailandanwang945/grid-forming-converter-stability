from __future__ import annotations

import unittest

from fastapi.testclient import TestClient

from backend.api.app import app
from backend.core.reduced_order_presets import (
    analytic_critical_damping,
    get_reduced_order_preset,
)
from backend.core.reduced_order_scan import (
    MAX_SCAN_POINTS,
    ReducedOrderScanError,
    scan_damping_reactance,
)


class ReducedOrderScanTest(unittest.TestCase):
    def setUp(self) -> None:
        self.topology = get_reduced_order_preset(
            "reduced-smib-stable"
        ).build_topology()

    def test_scan_resolves_unstable_marginal_and_stable_regions(self) -> None:
        original = self.topology.model_dump(mode="json")
        critical = analytic_critical_damping()

        scan = scan_damping_reactance(
            self.topology,
            target_vsm_id="gfm-1",
            target_line_id="line-grid",
            damping_values_pu=[0.05, critical, 60.0],
            reactance_values_pu=[0.2],
        )

        self.assertEqual(
            [row[0].stability for row in scan.rows],
            ["unstable", "marginal", "stable"],
        )
        self.assertEqual(
            scan.stability_counts,
            {"stable": 1, "marginal": 1, "unstable": 1},
        )
        self.assertEqual(scan.point_count, 3)
        for row, damping in zip(scan.rows, [0.05, critical, 60.0], strict=True):
            self.assertEqual(row[0].damping_coefficient_pu, damping)
            self.assertEqual(row[0].line_reactance_pu, 0.2)
            self.assertGreaterEqual(row[0].oscillation_frequency_hz, 0.0)

        self.assertEqual(self.topology.model_dump(mode="json"), original)

    def test_unknown_vsm_and_line_are_rejected(self) -> None:
        common = {
            "topology": self.topology,
            "damping_values_pu": [0.2],
            "reactance_values_pu": [0.2],
        }
        with self.assertRaisesRegex(ReducedOrderScanError, "目标 VSM.*不存在"):
            scan_damping_reactance(
                target_vsm_id="missing-vsm",
                target_line_id="line-grid",
                **common,
            )
        with self.assertRaisesRegex(ReducedOrderScanError, "目标线路.*不存在"):
            scan_damping_reactance(
                target_vsm_id="gfm-1",
                target_line_id="missing-line",
                **common,
            )

    def test_grid_size_limit_is_enforced_before_point_solves(self) -> None:
        damping = [0.01 * (index + 1) for index in range(51)]
        reactance = [0.01 * (index + 1) for index in range(50)]
        self.assertGreater(len(damping) * len(reactance), MAX_SCAN_POINTS)

        with self.assertRaisesRegex(ReducedOrderScanError, "超过上限 2500"):
            scan_damping_reactance(
                self.topology,
                target_vsm_id="gfm-1",
                target_line_id="line-grid",
                damping_values_pu=damping,
                reactance_values_pu=reactance,
            )

    def test_axes_must_be_strictly_increasing(self) -> None:
        with self.assertRaisesRegex(ReducedOrderScanError, "严格递增"):
            scan_damping_reactance(
                self.topology,
                target_vsm_id="gfm-1",
                target_line_id="line-grid",
                damping_values_pu=[0.2, 0.2],
                reactance_values_pu=[0.2],
            )


class ReducedOrderScanApiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.client = TestClient(app)

    def setUp(self) -> None:
        self.topology = get_reduced_order_preset(
            "reduced-smib-stable"
        ).build_topology().model_dump(mode="json")

    def test_api_returns_auditable_axes_points_and_scope(self) -> None:
        critical = analytic_critical_damping()
        response = self.client.post(
            "/api/reduced-order/scan",
            json={
                "topology": self.topology,
                "target_vsm_id": "gfm-1",
                "target_line_id": "line-grid",
                "damping_values_pu": [0.05, critical, 60.0],
                "reactance_values_pu": [0.2],
            },
        )

        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        scan = body["scan"]
        self.assertEqual(scan["axes"]["damping_values_pu"], [0.05, critical, 60.0])
        self.assertEqual(scan["axes"]["reactance_values_pu"], [0.2])
        self.assertEqual(scan["stability_counts"], {
            "stable": 1,
            "marginal": 1,
            "unstable": 1,
        })
        self.assertEqual(
            [row[0]["stability"] for row in scan["rows"]],
            ["unstable", "marginal", "stable"],
        )
        point = scan["rows"][0][0]
        self.assertIn("dominant_real_per_s", point)
        self.assertIn("oscillation_frequency_hz", point)
        self.assertIn("不把 X 自动换算或命名为短路比 SCR", body["model_scope"]["line_reactance_interpretation"])
        self.assertIn("不是论文小增益—小相位判据", body["model_scope"]["statement"])
        self.assertTrue(body["provenance"]["grid_is_explicit_not_interpolated"])
        self.assertFalse(body["provenance"]["input_topology_mutated"])

    def test_api_rejects_unknown_target_and_oversized_grid(self) -> None:
        invalid_target = self.client.post(
            "/api/reduced-order/scan",
            json={
                "topology": self.topology,
                "target_vsm_id": "missing",
                "target_line_id": "line-grid",
                "damping_values_pu": [0.2],
                "reactance_values_pu": [0.2],
            },
        )
        self.assertEqual(invalid_target.status_code, 422)
        self.assertIn("目标 VSM", invalid_target.text)

        oversized = self.client.post(
            "/api/reduced-order/scan",
            json={
                "topology": self.topology,
                "target_vsm_id": "gfm-1",
                "target_line_id": "line-grid",
                "damping_values_pu": [0.01 * (index + 1) for index in range(51)],
                "reactance_values_pu": [0.01 * (index + 1) for index in range(50)],
            },
        )
        self.assertEqual(oversized.status_code, 422)
        self.assertIn("超过上限 2500", oversized.text)


if __name__ == "__main__":
    unittest.main()
