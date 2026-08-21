"""Recompute the fixed common-inner-loop modal fingerprint and flat CSV."""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.core.sienna_team_inner_loop_modal_fingerprint import (  # noqa: E402
    run_common_inner_loop_modal_fingerprint,
)


CSV_COLUMNS = (
    "variant",
    "state_count",
    "factor_name",
    "factor",
    "tracking_status",
    "real_per_s",
    "imag_per_s",
    "oscillation_frequency_hz",
    "real_shift_from_baseline_per_s",
    "frequency_shift_from_baseline_hz",
    "lcl_group_total",
    "control_state_group_total",
    "voltage_pi_participation",
    "current_pi_participation",
    "active_damping_filter_participation",
    "converter_current_participation",
    "capacitor_voltage_participation",
    "grid_side_filter_current_participation",
    "condition_number",
    "maximum_eigenpair_residual",
    "minimum_right_mac",
    "minimum_left_mac",
    "maximum_normalized_eigenvalue_distance",
    "path_steps_including_rejected_direct_attempts",
)


def _row(
    *,
    variant_key: str,
    variant: dict,
    factor_name: str,
    factor: float,
    tracking_status: str,
    evidence: dict,
    real_shift: float,
    frequency_shift: float,
    minimum_right_mac: float | None,
    minimum_left_mac: float | None,
    maximum_distance: float | None,
    path_steps: int,
) -> dict[str, object]:
    eigenvalue = evidence["eigenvalue"]
    participation = evidence["group_participation_frozen_coordinates"]
    return {
        "variant": variant_key,
        "state_count": variant["state_count"],
        "factor_name": factor_name,
        "factor": factor,
        "tracking_status": tracking_status,
        "real_per_s": eigenvalue["real_per_s"],
        "imag_per_s": eigenvalue["imag_per_s"],
        "oscillation_frequency_hz": eigenvalue["oscillation_frequency_hz"],
        "real_shift_from_baseline_per_s": real_shift,
        "frequency_shift_from_baseline_hz": frequency_shift,
        "lcl_group_total": evidence["lcl_group_total"],
        "control_state_group_total": evidence["control_state_group_total"],
        "voltage_pi_participation": participation["voltage_pi"],
        "current_pi_participation": participation["current_pi"],
        "active_damping_filter_participation": participation.get(
            "active_damping_filter", 0.0
        ),
        "converter_current_participation": participation["converter_current"],
        "capacitor_voltage_participation": participation["capacitor_voltage"],
        "grid_side_filter_current_participation": participation[
            "grid_side_filter_current"
        ],
        "condition_number": evidence["condition_number"],
        "maximum_eigenpair_residual": max(
            evidence["right_eigenpair_residual"],
            evidence["left_eigenpair_residual"],
        ),
        "minimum_right_mac": minimum_right_mac,
        "minimum_left_mac": minimum_left_mac,
        "maximum_normalized_eigenvalue_distance": maximum_distance,
        "path_steps_including_rejected_direct_attempts": path_steps,
    }


def _csv_rows(payload: dict) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for variant_key, variant in payload["variants"].items():
        baseline = variant["baseline_named_branch"]
        rows.append(
            _row(
                variant_key=variant_key,
                variant=variant,
                factor_name="baseline",
                factor=1.0,
                tracking_status="matched",
                evidence=baseline,
                real_shift=0.0,
                frequency_shift=0.0,
                minimum_right_mac=1.0,
                minimum_left_mac=1.0,
                maximum_distance=0.0,
                path_steps=0,
            )
        )
        for factor_name, factor_paths in variant["factor_paths"].items():
            for key, path in factor_paths.items():
                factor = float(key.removeprefix("factor_").replace("p", "."))
                rows.append(
                    _row(
                        variant_key=variant_key,
                        variant=variant,
                        factor_name=factor_name,
                        factor=factor,
                        tracking_status=path["status"],
                        evidence=path["endpoint"],
                        real_shift=path["real_shift_from_baseline_per_s"],
                        frequency_shift=path[
                            "frequency_shift_from_baseline_hz"
                        ],
                        minimum_right_mac=path["minimum_right_mac"],
                        minimum_left_mac=path["minimum_left_mac"],
                        maximum_distance=path[
                            "maximum_normalized_eigenvalue_distance"
                        ],
                        path_steps=path[
                            "path_steps_including_rejected_direct_attempts"
                        ],
                    )
                )
    return rows


def run_experiment(output_dir: Path) -> tuple[Path, Path]:
    payload = run_common_inner_loop_modal_fingerprint()
    if payload["status"] != "passed":
        raise RuntimeError("common inner-loop modal fingerprint failed")
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "common_inner_loop_modal_fingerprint.json"
    csv_path = output_dir / "common_inner_loop_modal_fingerprint.csv"
    json_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    rows = _csv_rows(payload)
    with csv_path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    return json_path, csv_path


def main() -> None:
    json_path, csv_path = run_experiment(
        PROJECT_ROOT / "results" / "sienna-team-isomorphism"
    )
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    print(
        "COMMON_INNER_LOOP_MODAL_FINGERPRINT_OK "
        f"variants={len(payload['variants'])} "
        "all_consistent="
        f"{payload['hypothesis_test']['consistent_in_all_four_variants']}"
    )
    print(json_path)
    print(csv_path)


if __name__ == "__main__":
    main()
