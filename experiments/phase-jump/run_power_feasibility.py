"""Exploratory witness search for the reduced OCP, not hardware validation."""

from __future__ import annotations

import hashlib
import json
import argparse
import platform
from pathlib import Path

import numpy as np
import scipy
from scipy.integrate import solve_ivp
from scipy.linalg import expm
from scipy.optimize import brentq

ROOT = Path(__file__).resolve().parents[2]
K = np.array([[0.0, -1.0], [1.0, 0.0]])
VG = np.array([1.0, 0.0])


def build_case(frequency_hz: float, pre_point: str) -> dict:
    wb = 2 * np.pi * frequency_hz
    lg = (1 / 3) / np.sqrt(1 + 1 / 36)
    rg = lg / 6
    l2, r2 = 0.15, 0.025
    lt, rt = lg + l2, rg + r2
    if pre_point == "poi":
        z2 = rg * rg + lg * lg
        norm2 = ((1 + 2 * rg) - np.sqrt((1 + 2 * rg) ** 2 - 4 * z2)) / (2 * z2)
        iss = np.array([1 - rg * norm2, lg * norm2])
    elif pre_point == "grid":
        iss = np.array([1.0, 0.0])
    else:
        raise ValueError(pre_point)
    vc_ss = VG + rt * iss + lt * K @ iss
    angle = np.deg2rad(-25)
    rotation = np.array(
        [[np.cos(angle), np.sin(angle)], [-np.sin(angle), np.cos(angle)]]
    )
    frozen = rotation @ vc_ss
    post_i = rotation @ iss
    a = -wb * rt / lt * np.eye(2) - wb * K
    b = wb / lt * (frozen - VG)
    ieq = -np.linalg.solve(a, b)

    def natural(t):
        return ieq + expm(a * t) @ (post_i - ieq)

    grid = np.linspace(0, 0.02, 2001)
    above = next(j for j, t in enumerate(grid) if np.linalg.norm(natural(t)) >= 1.2)
    tlim = brentq(
        lambda t: np.linalg.norm(natural(t)) - 1.2,
        grid[above - 1],
        grid[above],
        xtol=5e-16,
        rtol=1e-14,
    )
    i0 = natural(tlim)
    alpha, beta = lg / lt, l2 / lt
    correction = (l2 * rg - lg * r2) / lt
    ppre = float(np.dot(VG + rg * iss + lg * K @ iss, iss))
    p0 = float(np.dot(alpha * frozen + beta * VG + correction * i0, i0))
    return dict(
        wb=wb,
        lg=lg,
        rg=rg,
        lt=lt,
        rt=rt,
        alpha=alpha,
        beta=beta,
        correction=correction,
        iss=iss,
        frozen=frozen,
        i0=i0,
        ppre=ppre,
        p0=p0,
        tlim=tlim,
        frequency_hz=frequency_hz,
        pre_point=pre_point,
    )


def run_case(c: dict, vmax: float, epsilon: float, verify: bool = False) -> dict:
    wb, lt, rt = c["wb"], c["lt"], c["rt"]
    ppre, p0 = c["ppre"], c["p0"]
    i0, iss = c["i0"], c["iss"]
    u0 = c["frozen"]
    if vmax < np.linalg.norm(u0) - 1e-10:
        raise ValueError(
            "Voltage bound already excludes the required continuous initial input"
        )
    e0 = i0 / np.linalg.norm(i0)
    initial_tangent = float(np.dot(u0, K @ e0))

    def target_power(t):
        return ppre + (p0 - ppre) * np.exp(-t / epsilon)

    def fast_voltage(t, i):
        size = np.linalg.norm(i)
        e = i / size
        ur = (target_power(t) - c["beta"] * i[0] - c["correction"] * size**2) / (
            c["alpha"] * size
        )
        if abs(ur) > vmax + 1e-9:
            raise ValueError("Required radial voltage exceeds the declared bound")
        available = np.sqrt(max(0.0, vmax**2 - ur**2))
        blend = np.exp(-t / epsilon)
        # Initial tangential component reproduces the frozen-voltage input.
        ut = blend * initial_tangent - (1 - blend) * available
        return ur * e + ut * (K @ e)

    def rhs_fast(t, i):
        return wb / lt * (fast_voltage(t, i) - VG - rt * i) - wb * K @ i

    def event(_t, i):
        return float(i[0] + c["rg"] * np.dot(i, i) - ppre)

    event.terminal = True
    event.direction = 1
    first = solve_ivp(
        rhs_fast,
        (0, 0.02),
        i0,
        method="DOP853",
        rtol=2e-11,
        atol=2e-13,
        max_step=epsilon / 2,
        events=event,
        dense_output=True,
    )
    if not first.success or not len(first.t_events[0]):
        raise ValueError("First recovery segment did not complete")
    split = float(first.t[-1])
    mid = first.y[:, -1]
    mid_dq = rhs_fast(split, mid)[1]
    tau = 0.005
    delta_q = mid[1] - iss[1]
    correction_q = mid_dq + delta_q / tau

    def q_curve(t):
        z = t - split
        q = (
            iss[1]
            + delta_q * np.exp(-z / tau)
            + correction_q * z * np.exp(-z / epsilon)
        )
        dq = -delta_q / tau * np.exp(-z / tau) + correction_q * np.exp(-z / epsilon) * (
            1 - z / epsilon
        )
        return float(q), float(dq)

    def rhs_slow(t, d):
        q, dq = q_curve(t)
        if abs(d[0]) < 0.1:
            raise ValueError("Current d-axis approached the construction singularity")
        dd = (
            wb / c["lg"] * (target_power(t) - d[0] - c["rg"] * (d[0] ** 2 + q * q))
            - q * dq
        ) / d[0]
        return np.array([dd])

    second = solve_ivp(
        rhs_slow,
        (split, 0.06),
        mid[:1],
        method="DOP853",
        rtol=2e-11,
        atol=2e-13,
        max_step=0.00005,
        dense_output=True,
    )
    if not second.success:
        raise ValueError(second.message)

    def current(t):
        if t <= split:
            return first.sol(t)
        return np.array([second.sol(t)[0], q_curve(t)[0]])

    def slow_voltage(t):
        i = np.array([second.sol(t)[0], q_curve(t)[0]])
        di = np.array([rhs_slow(t, i[:1])[0], q_curve(t)[1]])
        return VG + rt * i + lt * K @ i + lt / wb * di

    def voltage(t):
        if t <= split:
            return fast_voltage(t, current(t))
        return slow_voltage(t)

    times = np.unique(
        np.concatenate(
            (np.linspace(0, 0.06, 12001), first.t, np.array([split, split + 1e-12]))
        )
    )
    currents = np.array([current(t) for t in times])
    inputs = np.array([voltage(t) for t in times])
    poi = c["alpha"] * inputs + c["beta"] * VG + c["correction"] * currents
    power = np.sum(poi * currents, axis=1)
    row = dict(
        frequency_hz=c["frequency_hz"],
        pre_point=c["pre_point"],
        vmax_pu=vmax,
        transition_time_s=epsilon,
        tlim_s=c["tlim"],
        phase2_split_s=split,
        ppre_pu=ppre,
        initial_phase2_power_pu=p0,
        initial_i=c["i0"].tolist(),
        steady_i=iss.tolist(),
        current_peak_pu=float(np.linalg.norm(currents, axis=1).max()),
        voltage_peak_pu=float(np.linalg.norm(inputs, axis=1).max()),
        power_min_pu=float(power.min()),
        power_target_error=float(
            np.max(np.abs(power - np.array([target_power(t) for t in times])))
        ),
        initial_voltage_jump=float(np.linalg.norm(voltage(0) - u0)),
        split_voltage_jump=float(
            np.linalg.norm(slow_voltage(split) - fast_voltage(split, mid))
        ),
        terminal_current_error=float(np.linalg.norm(current(0.06) - iss)),
        sample_count=len(times),
    )
    row["sampled_constraints_pass"] = bool(
        row["current_peak_pu"] <= 1.3 + 1e-8
        and row["voltage_peak_pu"] <= vmax + 1e-8
        and row["power_min_pu"] >= ppre - 1e-8
        and row["initial_voltage_jump"] < 1e-8
        and row["split_voltage_jump"] < 1e-10
    )
    if verify:
        errors = {}
        for method in ["DOP853", "Radau"]:

            def independent_rhs(t, i):
                return wb / lt * (voltage(t) - VG - rt * i) - wb * K @ i

            independent = solve_ivp(
                independent_rhs,
                (0, 0.06),
                i0,
                method=method,
                rtol=1e-10,
                atol=1e-12,
                max_step=0.000025,
                t_eval=times,
            )
            if not independent.success or independent.y.shape[1] != len(times):
                raise ValueError("Independent integration failed")
            errors[method] = float(np.max(np.abs(independent.y.T - currents)))
        row["prescribed_input_reintegration_errors"] = errors
    return row


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--full", action="store_true", help="Run the declared 36-case exploratory grid"
    )
    args = parser.parse_args()
    rows = []
    for pre_point in ["poi", "grid"] if args.full else ["poi"]:
        for frequency in [50.0, 60.0] if args.full else [60.0]:
            c = build_case(frequency, pre_point)
            for vmax in (
                [float(np.linalg.norm(c["frozen"])), 1.05, 1.1]
                if args.full
                else [float(np.linalg.norm(c["frozen"]))]
            ):
                for epsilon in [1e-5, 5e-5, 1e-4] if args.full else [5e-5]:
                    try:
                        rows.append(run_case(c, vmax, epsilon, verify=False))
                    except ValueError as exc:
                        rows.append(
                            dict(
                                pre_point=pre_point,
                                frequency_hz=frequency,
                                vmax_pu=vmax,
                                transition_time_s=epsilon,
                                sampled_constraints_pass=False,
                                failure=str(exc),
                            )
                        )
                    print(json.dumps(rows[-1]), flush=True)
    # Independent prescribed-input integration for one predeclared main case.
    c = build_case(60.0, "poi")
    checked = run_case(c, float(np.linalg.norm(c["frozen"])), 5e-5, verify=True)
    expected_pdf_hash = (
        "a3639891dce05a209ec98d39c34c77875abab552de32e66cd39e7f638da3a69f"
    )
    actual_pdf_hash = hashlib.sha256(
        (
            ROOT
            / "references/papers/Awal-et-al-2026-phase-jump-overload-arxiv-2607.07904v1.pdf"
        ).read_bytes()
    ).hexdigest()
    if actual_pdf_hash != expected_pdf_hash:
        raise ValueError("Source PDF does not match the registered v1 snapshot")
    if (
        not checked["sampled_constraints_pass"]
        or max(checked["prescribed_input_reintegration_errors"].values()) > 1e-7
    ):
        raise ValueError("Predeclared main witness failed the stated numerical checks")
    payload = dict(
        status="exploratory-reduced-model-only",
        scope="full-grid" if args.full else "predeclared-main-case-only",
        rows=rows,
        checked_case=checked,
        environment=dict(
            python=platform.python_version(),
            numpy=np.__version__,
            scipy=scipy.__version__,
        ),
        source_pdf_sha256=actual_pdf_hash,
        script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        caveats=[
            "Vmax and pre-power measurement point not fully specified by paper",
            "No semiconductor current, DC, LC-state or real control bandwidth validation",
            "Finite checks do not prove continuous-time extrema or worldwide novelty",
        ],
    )
    filename = "pilot-full.json" if args.full else "pilot.json"
    out = ROOT / "results/phase-jump-power-feasibility" / filename
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(payload, indent=2, allow_nan=False) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            dict(
                rows=len(rows),
                sampled_pass=sum(r["sampled_constraints_pass"] for r in rows),
                checked_case=checked,
            ),
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
