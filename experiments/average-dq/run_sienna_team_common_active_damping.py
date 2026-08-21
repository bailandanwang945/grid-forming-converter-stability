"""Recompute the common active-damping intermediate-model comparison."""

from __future__ import annotations

import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.core.sienna_team_common_active_damping import (  # noqa: E402
    sienna_team_common_active_damping_audit,
)
from backend.core.sienna_team_common_inner_loop import (  # noqa: E402
    CommonInnerLoopParameters,
)
from backend.core.sienna_test08_reference import (  # noqa: E402
    FROZEN_INITIAL_STATE,
    SiennaTest08Parameters,
)


def run_experiment(output_dir: Path) -> Path:
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
    payload = sienna_team_common_active_damping_audit(
        parameters,
        angle_rad=float(FROZEN_INITIAL_STATE[0]),
        active_damping_cutoff_rad_s=source.active_damping_cutoff_rad_s,
        active_damping_gain=source.active_damping_gain,
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "common_active_damping_comparison.json"
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    if payload["status"] != "passed":
        raise RuntimeError("common active-damping audit failed")
    return output_path


def main() -> None:
    output_path = run_experiment(
        PROJECT_ROOT / "results" / "sienna-team-isomorphism"
    )
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    omit = payload["variants"]["both_omit_resistive_drop_feedforward"]
    include = payload["variants"]["both_include_resistive_drop_feedforward"]
    print(
        "SIENNA_TEAM_COMMON_ACTIVE_DAMPING_OK "
        f"omit_delta={omit['spectral_abscissa_change_per_s']:.6g} "
        f"include_delta={include['spectral_abscissa_change_per_s']:.6g} "
        "hypothesis_supported="
        f"{payload['hypothesis_test']['supported_for_both_structural_paths']}"
    )
    print(output_path)


if __name__ == "__main__":
    main()
