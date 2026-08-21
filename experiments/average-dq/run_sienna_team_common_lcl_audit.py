"""Recompute the bounded Sienna--team common-LCL isomorphism artifact."""

from __future__ import annotations

import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.core.sienna_test08_reference import (  # noqa: E402
    sienna_test08_audit_payload,
)


def run_experiment(output_dir: Path) -> Path:
    """Recompute the fixed payload into a caller-controlled directory."""

    output_dir.mkdir(parents=True, exist_ok=True)
    payload = sienna_test08_audit_payload()["common_lcl_isomorphism"]
    output_path = output_dir / "common_lcl_isomorphism.json"
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    if payload["status"] != "passed":
        raise RuntimeError("Sienna--team common-LCL isomorphism audit failed")
    return output_path


def main() -> None:
    output_path = run_experiment(
        PROJECT_ROOT / "results" / "sienna-team-isomorphism"
    )
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    print(
        "SIENNA_TEAM_COMMON_LCL_OK "
        f"A={payload['results']['state_matrix_max_abs_difference_per_s']:.6g} "
        f"B={payload['results']['input_matrix_max_abs_difference_per_s']:.6g} "
        "counterexample_A="
        f"{payload['results']['counterfactual']['state_matrix_max_abs_difference_per_s']:.6g}"
    )
    print(output_path)


if __name__ == "__main__":
    main()
