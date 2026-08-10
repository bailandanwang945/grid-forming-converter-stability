"""Windows release launcher for the self-contained GFM platform."""

from __future__ import annotations

import argparse
import json
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


def _verify_frontend(url: str) -> None:
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


def _verify_pinned_analysis(url: str) -> None:
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


def _verify_domain_comparison(url: str) -> None:
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


def _wait_for_port_release(port: int, timeout_s: float = 5.0) -> bool:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if _port_is_available(port):
            return True
        time.sleep(0.1)
    return _port_is_available(port)


def run(port: int, *, open_browser: bool, smoke_test: bool) -> int:
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

    print(f"[GFM] Grid-Forming Converter Stability Platform {_build_label()}")
    print("[GFM] Starting the local analysis service...")
    thread.start()
    try:
        _wait_for_health(f"{url}/api/health")
        _verify_frontend(url)
        _verify_pinned_analysis(url)
        _verify_domain_comparison(url)
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
        return 0
    except Exception as error:
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
    arguments = parser.parse_args()
    if not 1024 <= arguments.port <= 65535:
        parser.error("--port must be between 1024 and 65535")
    return run(
        arguments.port,
        open_browser=not arguments.no_browser and not arguments.smoke_test,
        smoke_test=arguments.smoke_test,
    )


if __name__ == "__main__":
    sys.exit(main())
