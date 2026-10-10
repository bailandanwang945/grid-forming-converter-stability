"""Independent piecewise-polynomial extrema and prescribed-input replay.

No optimization is performed here. Floating-point roots and integration are
numerical verification, not rigorous interval bounds or hardware validation.
"""
import hashlib
import json
from pathlib import Path

import numpy as np
from numpy.polynomial import Polynomial as Poly
from scipy.integrate import solve_ivp
from scipy.interpolate import BSpline, PPoly

ROOT = Path(__file__).resolve().parents[2]
RESULT = ROOT / "results/phase-jump-power-feasibility/constrained-ocp-2026-10-05/result.json"
K = np.array([[0., -1.], [1., 0.]])
VG = np.array([1., 0.])


def extrema(poly):
    points = [0., 1.]
    for root in poly.deriv().roots():
        if abs(root.imag) < 1e-7 and 0 < root.real < 1:
            points.append(float(root.real))
    values = np.asarray(poly(points))
    lo, hi = int(np.argmin(values)), int(np.argmax(values))
    return float(values[lo]), float(values[hi]), points[lo], points[hi]


def vector_value(vector, x):
    return np.array([component(x) for component in vector])


def rotate(vector):
    return [-vector[1], vector[0]]


def norm_squared(vector):
    return sum((component * component for component in vector), Poly([0.]))


def polynomial_audit(knots, coefficients, case):
    coefficients = np.asarray(coefficients, dtype=float)
    if coefficients.ndim != 2 or coefficients.shape[1] != 2 or not np.all(np.isfinite(coefficients)):
        raise ValueError("Invalid coefficient matrix")
    spline = BSpline(knots, coefficients, 5)
    components = [PPoly.from_spline((knots, coefficients[:, j], 5)) for j in range(2)]
    rows = []
    crosscheck = 0.
    for j, (left, right) in enumerate(zip(components[0].x[:-1], components[0].x[1:])):
        width = float(right - left)
        if width <= 0:
            continue
        i = [Poly(component.c[:, j][::-1] * width ** np.arange(6)) for component in components]
        di = [component.deriv() / width for component in i]
        ki = rotate(i)
        vc = [VG[m] + case["rt"] * i[m] + case["lt"] * ki[m]
              + case["lt"] / case["wb"] * di[m] for m in range(2)]
        poi = [case["alpha"] * vc[m] + case["beta"] * VG[m] + case["correction"] * i[m] for m in range(2)]
        power = sum((poi[m] * i[m] for m in range(2)), Poly([0.]))
        for local in [0., .27, .71, 1.]:
            time = float(left + width * local)
            crosscheck = max(crosscheck, float(np.linalg.norm(vector_value(i, local) - spline(time))))
            direct_u = VG + case["rt"] * spline(time) + case["lt"] * K @ spline(time) + case["lt"] / case["wb"] * spline(time, nu=1)
            crosscheck = max(crosscheck, float(np.linalg.norm(vector_value(vc, local) - direct_u)))
        pmin, pmax, pmin_at, _ = extrema(power)
        _, imax2, _, imax_at = extrema(norm_squared(i))
        _, vmax2, _, vmax_at = extrema(norm_squared(vc))
        # Rf=0 diagnostic hardware, not an author parameter restoration.
        cf, x1, r1 = .02, .1, .01
        du = [component.deriv() / width for component in vc]
        ku = rotate(vc)
        i1 = [i[m] + cf / case["wb"] * du[m] + cf * ku[m] for m in range(2)]
        di1, ki1 = [component.deriv() / width for component in i1], rotate(i1)
        vi = [vc[m] + r1 * i1[m] + x1 * ki1[m] + x1 / case["wb"] * di1[m] for m in range(2)]
        rows.append(dict(start_s=float(left), end_s=float(right), minimum_power_pu=pmin,
            maximum_power_pu=pmax, minimum_power_at_s=float(left + width * pmin_at),
            current_peak_pu=float(np.sqrt(max(0., imax2))), current_peak_at_s=float(left + width * imax_at),
            voltage_peak_pu=float(np.sqrt(max(0., vmax2))), voltage_peak_at_s=float(left + width * vmax_at),
            hypothetical_inverter_current_peak_pu=float(np.sqrt(max(0., extrema(norm_squared(i1))[1]))),
            hypothetical_inverter_voltage_peak_pu=float(np.sqrt(max(0., extrema(norm_squared(vi))[1])))))
    if not rows or crosscheck > 1e-8:
        raise AssertionError(f"B-spline / piecewise polynomial mismatch: {crosscheck}")
    p = min(rows, key=lambda row: row["minimum_power_pu"])
    i = max(rows, key=lambda row: row["current_peak_pu"])
    u = max(rows, key=lambda row: row["voltage_peak_pu"])
    summary = dict(minimum_power_pu=p["minimum_power_pu"], minimum_power_at_s=p["minimum_power_at_s"],
        current_peak_pu=i["current_peak_pu"], current_peak_at_s=i["current_peak_at_s"],
        voltage_peak_pu=u["voltage_peak_pu"], voltage_peak_at_s=u["voltage_peak_at_s"],
        maximum_representation_difference=crosscheck,
        hypothetical_inverter_current_peak_pu=max(row["hypothetical_inverter_current_peak_pu"] for row in rows),
        hypothetical_inverter_voltage_peak_pu=max(row["hypothetical_inverter_voltage_peak_pu"] for row in rows))
    return summary, rows


def replay(knots, coefficients, case, include_lc=False):
    spline = BSpline(knots, np.asarray(coefficients), 5)
    wb, lt, rt = case["wb"], case["lt"], case["rt"]
    cf, x1, r1 = .02, .1, .01
    end = float(knots[-1])

    def voltage(t):
        i = spline(t)
        return VG + rt * i + lt * K @ i + lt / wb * spline(t, nu=1)

    def du(t):
        return rt * spline(t, nu=1) + lt * K @ spline(t, nu=1) + lt / wb * spline(t, nu=2)

    def inv_current(t):
        return spline(t) + cf / wb * du(t) + cf * K @ voltage(t)

    def inv_voltage(t):
        ddu = rt * spline(t, nu=2) + lt * K @ spline(t, nu=2) + lt / wb * spline(t, nu=3)
        di1 = spline(t, nu=1) + cf / wb * ddu + cf * K @ du(t)
        return voltage(t) + r1 * inv_current(t) + x1 * K @ inv_current(t) + x1 / wb * di1

    def rhs(t, state):
        if not include_lc:
            return wb / lt * (voltage(t) - VG - rt * state) - wb * K @ state
        i1, u, i2 = state[:2], state[2:4], state[4:]
        return np.concatenate((wb / x1 * (inv_voltage(t) - u - r1 * i1) - wb * K @ i1,
            wb / cf * (i1 - i2) - wb * K @ u, wb / lt * (u - VG - rt * i2) - wb * K @ i2))

    if include_lc:
        initial = np.concatenate((inv_current(0), voltage(0), spline(0)))
    else:
        initial = spline(0)
    times = np.unique(np.concatenate((np.linspace(0, end, 1001), np.asarray(knots))))
    result = {}
    for method in ["DOP853", "Radau"] if not include_lc else ["Radau"]:
        solution = solve_ivp(rhs, (0., end), initial, method=method, rtol=1e-10, atol=1e-12,
                             max_step=5e-5, t_eval=times)
        if not solution.success or len(solution.t) != len(times):
            raise AssertionError(f"Prescribed-input replay failed: {solution.message}")
        if include_lc:
            expected = np.asarray([np.concatenate((inv_current(t), voltage(t), spline(t))) for t in times]).T
        else:
            expected = spline(times).T
        error = float(np.max(np.abs(solution.y - expected)))
        if error > 1e-7:
            raise AssertionError(f"Prescribed-input replay mismatch: {error}")
        result[method] = dict(maximum_state_error_pu=error, evaluation_count=int(solution.nfev))
    return result


def main(result_path=RESULT):
    result_path = Path(result_path).resolve()
    if not result_path.is_relative_to(ROOT):
        raise ValueError("Result path escapes project")
    target = result_path.parent / "verification.json"
    if target.exists():
        raise FileExistsError(target)
    result = json.loads(result_path.read_text(encoding="utf-8"))
    if result["status"] not in ("complete", "incomplete-budget") or len(result["strategies"]) != 2:
        raise ValueError("Incomplete comparison")
    for name, expected in result["source_hashes"].items():
        path = (ROOT / name.replace("\\", "/")).resolve()
        if not path.is_relative_to(ROOT) or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise AssertionError(f"Source mismatch: {name}")
    case = result["case"]
    rows = []
    for strategy in result["strategies"]:
        summary, segments = polynomial_audit(strategy["knots_s"], strategy["coefficients"], case)
        iok = summary["current_peak_pu"] <= 1.3 + 1e-7
        vok = summary["voltage_peak_pu"] <= np.linalg.norm(case["frozen"]) + 1e-7
        pok = summary["minimum_power_pu"] >= case["ppre"] - 1e-7
        row = dict(strategy=strategy["strategy"], polynomial_summary=summary, segments=segments,
                   current_pass=bool(iok), voltage_pass=bool(vok), power_pass=bool(pok))
        # Confirm sampled extrema are bounded by the separately obtained roots.
        dense = strategy["dense_check"]
        if dense["current_peak_pu"] > summary["current_peak_pu"] + 1e-7 or dense["voltage_peak_pu"] > summary["voltage_peak_pu"] + 1e-7 or dense["power_min_pu"] < summary["minimum_power_pu"] - 1e-7:
            raise AssertionError("Polynomial extrema missed dense sample violation")
        if iok and vok and pok and strategy["dense_check"]["endpoint_pass"]:
            row["independent_RL_replay"] = replay(strategy["knots_s"], strategy["coefficients"], case)
            row["hypothetical_LC_replay"] = replay(strategy["knots_s"], strategy["coefficients"], case, include_lc=True)
        rows.append(row)
    verified = dict(status="verified", result_sha256=hashlib.sha256(result_path.read_bytes()).hexdigest(),
        script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), strategies=rows,
        scope="floating-point polynomial extrema and optional prescribed-input replays; not strict interval proof or hardware ratings validation")
    target.write_text(json.dumps(verified, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    saved = json.loads(target.read_text(encoding="utf-8"))
    if saved["status"] != "verified" or len(saved["strategies"]) != 2:
        raise AssertionError("Verification readback failed")
    print(json.dumps({"status": saved["status"], "strategies": [{k: v for k, v in row.items() if k != "segments"} for row in rows]}, indent=2))


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("result", nargs="?", type=Path, default=RESULT)
    main(parser.parse_args().result)
