"""Recompute the two shared-power-port common outer-loop cases."""

from __future__ import annotations

import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.core.sienna_team_common_outer_loop import (  # noqa: E402
    run_common_outer_loop_audit,
)


def run_experiment(output_dir: Path) -> Path:
    payload = run_common_outer_loop_audit()
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "common_outer_loop_power_ports.json"
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    if payload["status"] != "passed":
        raise RuntimeError("common outer-loop audit failed")
    return output_path


def main() -> None:
    output_path = run_experiment(
        PROJECT_ROOT / "results" / "sienna-team-isomorphism"
    )
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    capacitor = payload["variants"]["filter_capacitor"]
    pcc = payload["variants"]["pcc"]
    print(
        "SIENNA_TEAM_COMMON_OUTER_LOOP_OK "
        f"capacitor_alpha={capacitor['spectral_abscissa_per_s']:.6g} "
        f"pcc_alpha={pcc['spectral_abscissa_per_s']:.6g} "
        "mixed_port_difference="
        f"{payload['counterexample']['state_matrix_max_abs_difference_per_s']:.6g}"
    )
    print(output_path)


if __name__ == "__main__":
    main()
