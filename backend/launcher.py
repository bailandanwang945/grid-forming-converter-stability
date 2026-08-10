"""Windows release launcher for the self-contained GFM platform."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import platform
from pathlib import Path
import socket
import sys
import threading
import time
import urllib.request
import webbrowser
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

import uvicorn

from backend.production_app import bundled_root, create_production_app


HOST = "127.0.0.1"
DEFAULT_PORT = 8000


def _build_label() -> str:
    metadata_file = bundled_root() / "build_info.json"
    try:
        metadata = json.loads(metadata_file.read_text(encoding="utf-8-sig"))
        return f"{metadata['version']} ({metadata['commit']})"
    except (FileNotFoundError, KeyError, json.JSONDecodeError, OSError):
        return "development"


def _port_is_available(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        return probe.connect_ex((HOST, port)) != 0


def _wait_for_health(url: str, timeout_s: float = 30.0) -> None:
    deadline = time.monotonic() + timeout_s
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1.0) as response:
                payload = json.loads(response.read().decode("utf-8"))
                if response.status == 200 and payload.get("status") == "ok":
                    return
        except Exception as error:  # Startup failures are reported after timeout.
            last_error = error
        time.sleep(0.2)
    raise RuntimeError(f"Service health check timed out: {last_error}")


class _AssetReferenceParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.references: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag == "script" and attributes.get("src"):
            self.references.append(str(attributes["src"]))
        if tag == "link" and attributes.get("href"):
            self.references.append(str(attributes["href"]))


def _verify_frontend(url: str) -> dict[str, object]:
    with urllib.request.urlopen(url, timeout=5.0) as response:
        html = response.read().decode("utf-8")
        if response.status != 200 or "<div id=\"root\"></div>" not in html:
            raise RuntimeError("Production index.html is unavailable or invalid.")
    parser = _AssetReferenceParser()
    parser.feed(html)
    local_assets = [
        reference
        for reference in parser.references
        if urlparse(reference).scheme in ("", "http", "https")
        and urlparse(urljoin(url, reference)).hostname in (HOST, "localhost")
    ]
    if not any(reference.split("?", 1)[0].endswith(".js") for reference in local_assets):
        raise RuntimeError("Production index.html does not reference a JavaScript bundle.")
    for reference in local_assets:
        asset_url = urljoin(url, reference)
        with urllib.request.urlopen(asset_url, timeout=5.0) as response:
            if response.status != 200 or not response.read(1):
                raise RuntimeError(f"Frontend asset is unavailable: {reference}")
    return {"index": "passed", "local_asset_count": len(local_assets)}


def _verify_pinned_analysis(url: str) -> dict[str, object]:
    request = urllib.request.Request(
        f"{url}/api/analysis/run",
        data=json.dumps({"scenario_id": "fig8_D_0p05"}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=30.0) as response:
        payload = json.loads(response.read().decode("utf-8"))
    summary = payload.get("summary", {})
    if (
        response.status != 200
        or summary.get("closed_loop_reference") != "unstable"
        or summary.get("uncovered_points") != 75
        or summary.get("frequency_points") != 1000
    ):
        raise RuntimeError("Packaged Fig. 8 baseline verification failed.")
    return {
        "scenario_id": payload.get("scenario_id"),
        "closed_loop_reference": summary.get("closed_loop_reference"),
        "uncovered_points": summary.get("uncovered_points"),
        "frequency_points": summary.get("frequency_points"),
    }


def _verify_domain_comparison(url: str) -> dict[str, object]:
    with urllib.request.urlopen(
        f"{url}/api/comparison/fig8-domain", timeout=10.0
    ) as response:
        payload = json.loads(response.read().decode("utf-8"))
    counts = payload.get("summary", {}).get("classificationCounts", {})
    if (
        response.status != 200
        or payload.get("status") != "completed"
        or len(payload.get("rows", [])) != 176
        or counts.get("criterionCoveredStable") != 45
        or counts.get("stableNotCovered") != 96
        or counts.get("unstableNotCovered") != 35
        or counts.get("numericalPending") != 0
        or counts.get("consistencyViolation") != 0
    ):
        raise RuntimeError("Packaged Fig. 8 same-domain evidence verification failed.")
    return {"point_count": len(payload["rows"]), "classification_counts": counts}


def _verify_reduced_order_workflow(url: str) -> dict[str, object]:
    request_payload = {
        "preset_id": "reduced-smib-stable",
        "simulation_time_s": 1.0,
        "time_step_s": 0.1,
        "initial_angle_perturbation_rad": 0.001,
    }
    request = urllib.request.Request(
        f"{url}/api/reduced-order/analyze",
        data=json.dumps(request_payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=30.0) as response:
        payload = json.loads(response.read().decode("utf-8"))
    result = payload.get("result", {})
    validation = payload.get("input_validation", {})
    if (
        response.status != 200
        or payload.get("status") != "completed"
        or validation.get("status") != "passed"
        or result.get("stability") != "stable"
        or len(result.get("poles", [])) != 3
    ):
        raise RuntimeError("Packaged reduced-order analysis verification failed.")

    report_request = urllib.request.Request(
        f"{url}/api/reports/reduced-order",
        data=json.dumps(request_payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(report_request, timeout=30.0) as response:
        report = response.read().decode("utf-8")
    if (
        response.status != 200
        or "不是完整 dq 模型结论" not in report
        or "输入拓扑与参数" not in report
    ):
        raise RuntimeError("Packaged reduced-order report verification failed.")
    return {
        "preset_id": request_payload["preset_id"],
        "stability": result["stability"],
        "pole_count": len(result["poles"]),
        "report": "passed",
    }


def _verify_average_dq_workflow(url: str) -> dict[str, object]:
    request_payload = {
        "preset_id": "average-dq-smib-verification",
        "simulation_time_s": 0.02,
        "time_step_s": 0.002,
        "initial_angle_perturbation_rad": 0.0001,
        "frequency_values_hz": [0.1, 1.0, 10.0],
    }
    request = urllib.request.Request(
        f"{url}/api/average-dq/analyze",
        data=json.dumps(request_payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=30.0) as response:
        payload = json.loads(response.read().decode("utf-8"))
    result = payload.get("result", {})
    operating = payload.get("operating_point", {})
    reduction = result.get("quasisteady_reduction_comparison", {})
    if (
        response.status != 200
        or payload.get("status") != "completed"
        or result.get("stability") != "stable"
        or len(result.get("poles", [])) != 16
        or operating.get("closed_rhs_residual_inf", 1.0) >= 1.0e-9
        or abs(operating.get("active_power_balance_residual_pu", 1.0)) >= 1.0e-8
        or result.get("port_interconnection_max_abs_error", 1.0) >= 1.0e-6
        or reduction.get("oscillation_frequency_relative_error", 1.0) >= 0.05
        or reduction.get("decay_rate_relative_error", 1.0) >= 0.05
    ):
        raise RuntimeError("Packaged average-dq analysis verification failed.")

    report_request = urllib.request.Request(
        f"{url}/api/reports/average-dq",
        data=json.dumps(request_payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(report_request, timeout=30.0) as response:
        report = response.read().decode("utf-8")
    if (
        response.status != 200
        or "端口互联误差" not in report
        or "不是论文算例复现" not in report
        or "不宣称完成工程模型确认" not in report
    ):
        raise RuntimeError("Packaged average-dq report verification failed.")
    return {
        "preset_id": request_payload["preset_id"],
        "stability": result["stability"],
        "pole_count": len(result["poles"]),
        "closed_rhs_residual_inf": operating["closed_rhs_residual_inf"],
        "active_power_balance_residual_pu": operating[
            "active_power_balance_residual_pu"
        ],
        "port_interconnection_max_abs_error": result[
            "port_interconnection_max_abs_error"
        ],
        "reduction_frequency_relative_error": reduction[
            "oscillation_frequency_relative_error"
        ],
        "reduction_decay_relative_error": reduction["decay_rate_relative_error"],
        "report": "passed",
    }


def _write_runtime_evidence(path: str, payload: dict[str, object]) -> None:
    evidence_path = Path(path).expanduser().resolve()
    evidence_path.parent.mkdir(parents=True, exist_ok=True)
    evidence_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _wait_for_port_release(port: int, timeout_s: float = 5.0) -> bool:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if _port_is_available(port):
            return True
        time.sleep(0.1)
    return _port_is_available(port)


def run(
    port: int,
    *,
    open_browser: bool,
    smoke_test: bool,
    evidence_file: str | None = None,
) -> int:
    if not _port_is_available(port):
        print(f"[GFM] Port {port} is already in use. Close the other service and retry.")
        return 2

    url = f"http://{HOST}:{port}"
    application = create_production_app()
    config = uvicorn.Config(
        application,
        host=HOST,
        port=port,
        log_level="warning",
        access_log=False,
    )
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, name="gfm-local-server", daemon=True)

    build_label = _build_label()
    evidence: dict[str, object] = {
        "schema_version": "gfm-runtime-acceptance/1.1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "build_label": build_label,
        "platform": platform.platform(),
        "port": port,
        "status": "running",
        "checks": {},
    }
    print(f"[GFM] Grid-Forming Converter Stability Platform {build_label}")
    print("[GFM] Starting the local analysis service...")
    thread.start()
    try:
        _wait_for_health(f"{url}/api/health")
        evidence["checks"] = {
            "health": "passed",
            "frontend": _verify_frontend(url),
            "fig8": _verify_pinned_analysis(url),
            "same_domain": _verify_domain_comparison(url),
            "reduced_order": _verify_reduced_order_workflow(url),
            "average_dq": _verify_average_dq_workflow(url),
        }
        evidence["status"] = "passed"
        if evidence_file:
            _write_runtime_evidence(evidence_file, evidence)
        print(f"[GFM] Ready: {url}")
        if open_browser:
            webbrowser.open(url)
        if smoke_test:
            print("GFM_RELEASE_SMOKE_OK")
            return 0
        print("[GFM] Keep this window open. Press Enter or Ctrl+C to exit.")
        input()
        return 0
    except KeyboardInterrupt:
        evidence["status"] = "interrupted"
        if evidence_file:
            _write_runtime_evidence(evidence_file, evidence)
        return 0
    except Exception as error:
        evidence["status"] = "failed"
        evidence["error"] = str(error)
        if evidence_file:
            _write_runtime_evidence(evidence_file, evidence)
        print(f"[GFM] Startup failed: {error}")
        return 1
    finally:
        print("[GFM] Stopping the local service...")
        server.should_exit = True
        thread.join(timeout=10.0)
        if thread.is_alive():
            server.force_exit = True
            thread.join(timeout=3.0)
        if not _wait_for_port_release(port):
            print(f"[GFM] Warning: port {port} was not released in time.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--smoke-test", action="store_true")
    parser.add_argument(
        "--evidence-file",
        help="write machine-readable runtime acceptance evidence to this JSON file",
    )
    arguments = parser.parse_args()
    if not 1024 <= arguments.port <= 65535:
        parser.error("--port must be between 1024 and 65535")
    return run(
        arguments.port,
        open_browser=not arguments.no_browser and not arguments.smoke_test,
        smoke_test=arguments.smoke_test,
        evidence_file=arguments.evidence_file,
    )


if __name__ == "__main__":
    sys.exit(main())
