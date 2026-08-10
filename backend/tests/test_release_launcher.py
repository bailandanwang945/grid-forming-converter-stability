from __future__ import annotations

import json
import socket
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, Response

from backend.launcher import run


def acceptance_app() -> FastAPI:
    app = FastAPI()

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/")
    def index() -> HTMLResponse:
        return HTMLResponse(
            '<!doctype html><div id="root"></div>'
            '<script src="/assets/app.js"></script>'
        )

    @app.get("/assets/app.js")
    def asset() -> Response:
        return Response("console.log('ok')", media_type="text/javascript")

    @app.post("/api/analysis/run")
    def fig8() -> dict:
        return {
            "scenario_id": "fig8_D_0p05",
            "summary": {
                "closed_loop_reference": "unstable",
                "uncovered_points": 75,
                "frequency_points": 1000,
            },
        }

    @app.get("/api/comparison/fig8-domain")
    def comparison() -> dict:
        return {
            "status": "completed",
            "rows": [{}] * 176,
            "summary": {
                "classificationCounts": {
                    "criterionCoveredStable": 45,
                    "stableNotCovered": 96,
                    "unstableNotCovered": 35,
                    "numericalPending": 0,
                    "consistencyViolation": 0,
                }
            },
        }

    @app.post("/api/reduced-order/analyze")
    def reduced_order() -> dict:
        return {
            "status": "completed",
            "input_validation": {"status": "passed"},
            "result": {
                "stability": "stable",
                "poles": [{}, {}, {}],
            },
        }

    @app.post("/api/reports/reduced-order")
    def reduced_order_report() -> HTMLResponse:
        return HTMLResponse("输入拓扑与参数；不是完整 dq 模型结论")

    return app


class ReleaseLauncherTest(unittest.TestCase):
    def test_smoke_writes_cross_machine_runtime_evidence(self) -> None:
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            port = int(probe.getsockname()[1])

        with tempfile.TemporaryDirectory() as directory:
            evidence_path = Path(directory) / "runtime-evidence.json"
            with patch(
                "backend.launcher.create_production_app",
                return_value=acceptance_app(),
            ):
                exit_code = run(
                    port,
                    open_browser=False,
                    smoke_test=True,
                    evidence_file=str(evidence_path),
                )

            self.assertEqual(exit_code, 0)
            evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
            self.assertEqual(evidence["status"], "passed")
            self.assertEqual(
                evidence["checks"]["fig8"]["uncovered_points"],
                75,
            )
            self.assertEqual(
                evidence["checks"]["same_domain"]["point_count"],
                176,
            )
            self.assertEqual(
                evidence["checks"]["reduced_order"]["stability"],
                "stable",
            )
            self.assertEqual(
                evidence["checks"]["reduced_order"]["report"],
                "passed",
            )


if __name__ == "__main__":
    unittest.main()
