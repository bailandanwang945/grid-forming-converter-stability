"""Recompute the bounded Sienna--team inner-control mapping artifact."""

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
    """Recompute the fixed mapping into a caller-controlled directory."""

    output_dir.mkdir(parents=True, exist_ok=True)
    payload = sienna_test08_audit_payload()["inner_control_mapping"]
    output_path = output_dir / "inner_control_mapping.json"
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    if payload["pi_state_mapping"]["status"] != "passed":
        raise RuntimeError("Sienna--team PI state mapping failed")
    if payload["compensation_mapping"]["parameter_only_isomorphic"]:
        raise RuntimeError("expected structural compensation gap disappeared")
    if not payload["compensation_mapping"]["structural_counterfactual_passed"]:
        raise RuntimeError("declared structural counterfactual did not close")
    return output_path


def main() -> None:
    output_path = run_experiment(
        PROJECT_ROOT / "results" / "sienna-team-isomorphism"
    )
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    compensation = payload["compensation_mapping"]
    print(
        "SIENNA_TEAM_INNER_CONTROL_MAPPING_OK "
        f"pi={payload['pi_state_mapping']['status']} "
        "parameter_aligned_gap="
        f"{compensation['parameter_only_aligned_max_abs_difference']:.6g}"
    )
    print(output_path)


if __name__ == "__main__":
    main()
