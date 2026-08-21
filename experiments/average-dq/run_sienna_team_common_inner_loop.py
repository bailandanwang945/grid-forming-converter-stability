"""Recompute the two-path Sienna--team common inner-loop audit."""

from __future__ import annotations

import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.core.sienna_team_common_inner_loop import (  # noqa: E402
    CommonInnerLoopParameters,
    sienna_team_common_inner_loop_audit,
)
from backend.core.sienna_test08_reference import (  # noqa: E402
    FROZEN_INITIAL_STATE,
    SiennaTest08Parameters,
)


def run_experiment(output_dir: Path) -> Path:
    """Recompute the fixed two-variant artifact."""

    source = SiennaTest08Parameters()
    parameters = CommonInnerLoopParameters(
        frequency_hz=source.frequency_hz,
        voltage_kp=source.voltage_kp,
        voltage_ki_per_s=source.voltage_ki,
        current_kp=source.current_kp,
        current_ki_per_s=source.current_ki,
        converter_side_resistance_pu=source.converter_side_resistance_pu,
        converter_side_reactance_pu=source.converter_side_reactance_pu,
        filter_capacitor_susceptance_pu=source.filter_capacitor_susceptance_pu,
        grid_side_resistance_pu=source.grid_side_resistance_pu,
        grid_side_reactance_pu=source.grid_side_reactance_pu,
        virtual_resistance_pu=source.virtual_resistance_pu,
        virtual_reactance_pu=source.virtual_reactance_pu,
        resistive_drop_feedforward_gain=0.0,
        synchronous_frequency_pu=source.system_frequency_pu,
    )
    payload = sienna_team_common_inner_loop_audit(
        parameters, angle_rad=float(FROZEN_INITIAL_STATE[0])
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "common_inner_loop_variants.json"
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    if payload["status"] != "passed":
        raise RuntimeError("Sienna--team common inner-loop audit failed")
    return output_path


def main() -> None:
    output_path = run_experiment(
        PROJECT_ROOT / "results" / "sienna-team-isomorphism"
    )
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    sensitivity = payload["structural_choice_sensitivity"]
    print(
        "SIENNA_TEAM_COMMON_INNER_LOOP_OK "
        f"max_eigenvalue_shift={sensitivity['maximum_matched_eigenvalue_displacement_per_s']:.6g} "
        f"abscissa_change={sensitivity['spectral_abscissa_change_per_s']:.6g}"
    )
    print(output_path)


if __name__ == "__main__":
    main()
