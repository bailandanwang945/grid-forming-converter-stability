from __future__ import annotations

import unittest

from fastapi.testclient import TestClient

from backend.api.app import app


class AnalysisApiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.client = TestClient(app)

    def test_health(self) -> None:
        response = self.client.get("/api/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")
        self.assertEqual(response.json()["version"], "0.3.0-rc5")

    def test_scenarios_are_explicitly_pinned(self) -> None:
        response = self.client.get("/api/scenarios")
        self.assertEqual(response.status_code, 200)
        scenario_ids = [value["id"] for value in response.json()["scenarios"]]
        self.assertEqual(scenario_ids, ["fig8_D_0p05", "fig8_D_0p5"])

    def test_author_cases_use_portable_regression_kernel(self) -> None:
        unstable = self.client.post(
            "/api/analysis/run", json={"scenario_id": "fig8_D_0p05"}
        )
        stable = self.client.post(
            "/api/analysis/run", json={"scenario_id": "fig8_D_0p5"}
        )
        self.assertEqual(unstable.status_code, 200)
        self.assertEqual(stable.status_code, 200)
        unstable_body = unstable.json()
        stable_body = stable.json()
        self.assertEqual(unstable_body["summary"]["closed_loop_reference"], "unstable")
        self.assertEqual(stable_body["summary"]["closed_loop_reference"], "stable")
        self.assertEqual(unstable_body["summary"]["uncovered_points"], 75)
        self.assertEqual(stable_body["summary"]["uncovered_points"], 0)
        self.assertEqual(
            unstable_body["provenance"]["mode"],
            "portable-pinned-author-fixture",
        )
        self.assertEqual(
            unstable_body["summary"]["frequency_discrepancy_status"], "unresolved"
        )

    def test_unknown_scenario_is_rejected_by_contract(self) -> None:
        response = self.client.post(
            "/api/analysis/run", json={"scenario_id": "made-up-case"}
        )
        self.assertEqual(response.status_code, 422)

    def test_printable_report_contains_result_and_provenance(self) -> None:
        response = self.client.get(
            "/api/reports/fig8", params={"scenario_id": "fig8_D_0p05"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/html", response.headers["content-type"])
        self.assertIn("0.578113", response.text)
        self.assertIn("1.2", response.text)
        self.assertIn("75 / 1000", response.text)
        self.assertIn("ef67c7a4ac84e4e1142e95b072d241db89eb64ba", response.text)


if __name__ == "__main__":
    unittest.main()
