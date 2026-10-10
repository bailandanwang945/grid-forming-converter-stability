"""Fixed six-duration quintic repair, with polynomial extrema and LC demands."""
import hashlib
import json
import time
from pathlib import Path

import numpy as np
from numpy.polynomial import Polynomial as Poly

from run_power_feasibility import K, ROOT, VG, build_case

OUTPUT = ROOT / "results/phase-jump-power-feasibility/c1-repair-2026-10-05.json"


def vector_value(vector, x):
    return np.array([component(x) for component in vector])


def rotate(vector):
    return [-vector[1], vector[0]]


def norm_squared(vector):
    return sum((p * p for p in vector), Poly([0]))


def extrema(poly):
    roots = poly.deriv().roots()
    points = [0., 1.] + [float(r.real) for r in roots if abs(r.imag) < 1e-7 and 0 < r.real < 1]
    values = np.asarray(poly(points))
    grid = np.asarray(poly(np.linspace(0, 1, 10001)))
    if min(values) > min(grid) + 1e-7 or max(values) < max(grid) - 1e-7:
        raise AssertionError("Stationary-point extrema missed sampled extrema")
    return float(min(values)), float(max(values))


def trajectory(case, duration):
    i0, u0 = case["i0"], case["frozen"]
    a = -case["wb"] * case["rt"] / case["lt"] * np.eye(2) - case["wb"] * K
    di0 = a @ i0 + case["wb"] / case["lt"] * (u0 - VG)
    ddi0 = a @ di0
    initial = np.array([i0, duration * di0, duration**2 * ddi0 / 2])
    system = np.array([[1, 1, 1], [3, 4, 5], [6, 12, 20]], float)
    rhs = np.array([case["iss"] - initial.sum(axis=0), -initial[1] - 2 * initial[2], -2 * initial[2]])
    coefficients = np.vstack([initial, np.linalg.solve(system, rhs)])
    current = [Poly(coefficients[:, j]) for j in range(2)]
    di = [p.deriv() / duration for p in current]
    ki = rotate(current)
    voltage = [VG[j] + case["rt"] * current[j] + case["lt"] * ki[j]
               + case["lt"] / case["wb"] * di[j] for j in range(2)]
    return current, voltage


def evaluate(case, duration):
    current, voltage = trajectory(case, duration)
    du = [p.deriv() / duration for p in voltage]
    cf, x1, r1 = .02, .1, .01  # Hypothetical diagnostics, not author hardware.
    ku = rotate(voltage)
    inverter_current = [current[j] + cf / case["wb"] * du[j] + cf * ku[j] for j in range(2)]
    di1 = [p.deriv() / duration for p in inverter_current]
    ki1 = rotate(inverter_current)
    inverter_voltage = [voltage[j] + r1 * inverter_current[j] + x1 * ki1[j]
                        + x1 / case["wb"] * di1[j] for j in range(2)]
    poi = [case["alpha"] * voltage[j] + case["beta"] * VG[j] + case["correction"] * current[j] for j in range(2)]
    power = sum((poi[j] * current[j] for j in range(2)), Poly([0]))
    start_voltage_error = np.linalg.norm(vector_value(voltage, 0) - case["frozen"])
    end_voltage = VG + case["rt"] * case["iss"] + case["lt"] * K @ case["iss"]
    endpoint_errors = dict(start_voltage=float(start_voltage_error),
        end_voltage=float(np.linalg.norm(vector_value(voltage, 1) - end_voltage)),
        start_voltage_derivative=float(np.linalg.norm(vector_value(du, 0))),
        end_voltage_derivative=float(np.linalg.norm(vector_value(du, 1))),
        start_current=float(np.linalg.norm(vector_value(current, 0) - case["i0"])),
        end_current=float(np.linalg.norm(vector_value(current, 1) - case["iss"])))
    if max(endpoint_errors.values()) > 1e-7:
        raise AssertionError(f"Endpoint matching failed: {endpoint_errors}")
    current_peak = np.sqrt(max(0., extrema(norm_squared(current))[1]))
    voltage_peak = np.sqrt(max(0., extrema(norm_squared(voltage))[1]))
    pmin = extrema(power)[0]
    violations = []
    if current_peak > 1.3 + 1e-8:
        violations.append("grid_current")
    if voltage_peak > np.linalg.norm(case["frozen"]) + 1e-8:
        violations.append("capacitor_voltage")
    if pmin < case["ppre"] - 1e-8:
        violations.append("poi_active_power")
    return dict(duration_s=duration, reduced_constraints_satisfied=not violations,
        violations=violations, current_peak_pu=float(current_peak), capacitor_voltage_peak_pu=float(voltage_peak),
        poi_minimum_active_power_pu=float(pmin), endpoint_errors=endpoint_errors,
        hypothetical_inverter_current_peak_pu=float(np.sqrt(max(0., extrema(norm_squared(inverter_current))[1]))),
        hypothetical_inverter_voltage_peak_pu=float(np.sqrt(max(0., extrema(norm_squared(inverter_voltage))[1]))))


def main():
    if OUTPUT.exists():
        raise FileExistsError(OUTPUT)
    started = time.monotonic()
    sources = [Path(__file__), ROOT / "experiments/phase-jump/run_power_feasibility.py",
               ROOT / "results/phase-jump-power-feasibility/c1-repair-plan-2026-10-05.md"]
    before = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}
    case = build_case(60., "poi")
    rows = []
    for duration in [.001, .002, .005, .01, .02, .04]:
        if time.monotonic() - started > 30:
            raise TimeoutError("Fixed trial budget exceeded")
        row = evaluate(case, duration)
        rows.append(row)
        print(json.dumps(row), flush=True)
    if before != {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}:
        raise AssertionError("Sources changed during trial")
    found = any(row["reduced_constraints_satisfied"] for row in rows)
    result = dict(status="complete", source_hashes=before, rows=rows, elapsed_seconds=time.monotonic() - started,
                  decision="independent-LC-reintegration-required" if found else "stop-this-six-duration-quintic-repair",
                  hypothetical_hardware=dict(Cf_pu=.02, X1_pu=.1, R1_pu=.01),
                  scope="floating-point polynomial trajectory check; not strict feasibility proof or new control method")
    OUTPUT.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    saved = json.loads(OUTPUT.read_text(encoding="utf-8"))
    if saved["status"] != "complete" or len(saved["rows"]) != 6:
        raise AssertionError("Result readback failed")
    print(result["decision"])


if __name__ == "__main__":
    main()
