"""Write the fixed common static-network audit artifact."""

from __future__ import annotations

import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.core.sienna_team_common_static_network import (  # noqa: E402
    run_common_static_network_audit,
)


def run_experiment(output_dir: Path) -> Path:
    payload = run_common_static_network_audit()
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "common_static_network.json"
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    if payload["status"] != "passed":
        raise RuntimeError("common static-network audit failed")
    return output_path


def main() -> None:
    output_path = run_experiment(
        PROJECT_ROOT / "results" / "sienna-team-isomorphism"
    )
    print(output_path)


if __name__ == "__main__":
    main()
