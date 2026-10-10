"""Check an LC state-continuity obstruction in the reduced-model witness."""

import hashlib
import json
from pathlib import Path

import numpy as np

from run_power_feasibility import K, ROOT, VG, build_case


def check():
    c = build_case(60.0, "poi")
    i, u = c["i0"], c["frozen"]
    size = np.linalg.norm(i)
    e, ep = i / size, K @ (i / size)
    di = c["wb"] / c["lt"] * (u - VG - c["rt"] * i) - c["wb"] * K @ i
    radius_rate, angle_rate = e @ di, (ep @ di) / size
    ur, ut = u @ e, u @ ep
    epsilon, vmax = 5e-5, np.linalg.norm(u)
    power_rate = -(c["p0"] - c["ppre"]) / epsilon
    ur_rate = (power_rate - c["beta"] * di[0]) / (
        c["alpha"] * size
    ) - ur * radius_rate / size
    ut_rate = -(ut + np.sqrt(max(0.0, vmax**2 - ur**2))) / epsilon
    du = (ur_rate - ut * angle_rate) * e + (ut_rate + ur * angle_rate) * ep

    def independently_evaluate_initial_voltage(t):
        # Taylor approximation of the natural i(t); its error is O(t^2).
        z = i + t * di
        radius = np.linalg.norm(z)
        basis = z / radius
        target = c["ppre"] + (c["p0"] - c["ppre"]) * np.exp(-t / epsilon)
        radial = (target - c["beta"] * z[0]) / (c["alpha"] * radius)
        blend = np.exp(-t / epsilon)
        tangent = blend * ut - (1 - blend) * np.sqrt(max(0.0, vmax**2 - radial**2))
        return radial * basis + tangent * (K @ basis)

    relative_errors = {}
    for h in [1e-10, 1e-11]:
        finite = (independently_evaluate_initial_voltage(h) - u) / h
        relative_errors[str(h)] = float(
            np.linalg.norm(finite - du) / np.linalg.norm(du)
        )
    if (
        max(relative_errors.values()) > 1e-4
        or relative_errors["1e-11"] >= relative_errors["1e-10"]
    ):
        raise ValueError(
            "Voltage derivative formula failed finite-difference comparison: "
            + repr(relative_errors)
        )
    if np.linalg.norm(du) < 1:
        raise ValueError("Expected nonzero voltage derivative obstruction absent")
    rows = [
        dict(
            hypothetical_capacitance_pu=cf,
            required_inverter_current_jump_pu=float(np.linalg.norm(cf / c["wb"] * du)),
        )
        for cf in [0.0, 0.01, 0.02, 0.05]
    ]
    return dict(
        status="reject-as-direct-full-LC-trajectory",
        scope="initial-continuity-only",
        voltage_derivative_right_pu_per_s=du.tolist(),
        voltage_derivative_left_pu_per_s=[0.0, 0.0],
        finite_difference_relative_errors=relative_errors,
        rows=rows,
        explanation="i1=i2+Cf/wb*(dvc/dt-Omega*vc); nonzero dvc jump requires an impossible inductor-current jump for any Cf>0",
        caveats=[
            "This rejects this prescribed trajectory, not all feasible controllers",
            "Cf values are hypothetical diagnostic settings, not paper hardware values",
        ],
        script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        construction_sha256=hashlib.sha256(
            (ROOT / "experiments/phase-jump/run_power_feasibility.py").read_bytes()
        ).hexdigest(),
    )


if __name__ == "__main__":
    result = check()
    output = ROOT / "results/phase-jump-power-feasibility/lc_initial_regularity.json"
    output.write_text(
        json.dumps(result, indent=2, allow_nan=False) + "\n", encoding="utf-8"
    )
    print(json.dumps(result, indent=2))
