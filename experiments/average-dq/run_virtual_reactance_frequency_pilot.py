"""Fixed single-converter algebraic virtual-reactance frequency-factor pilot.

No production patch, author-model correction, two-machine or novelty claim.
Run from repository root; results stay in the dedicated pilot directory.
"""

from __future__ import annotations

import hashlib
import json
import platform
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import scipy
from scipy.linalg import eig

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
# Direct script execution needs the repository root before project imports.
from backend.core.average_dq_model import (  # noqa: E402
    build_average_dq_model,
    _closed_rhs,
    _references,
)
from backend.core.average_dq_presets import build_average_dq_ablation_anchor_case  # noqa: E402
from backend.core.average_dq_sampled_command import (  # noqa: E402
    sampled_command_matrices,
    split_average_dq_sampled_command,
)

J = np.array([[0.0, -1.0], [1.0, 0.0]])
VARIANTS = ("instantaneous-frequency", "fixed-nominal-frequency")
LINE_X = (0.2, 0.4)
VIRTUAL_X = (0.0, 0.1, 0.3)
PERIODS = (0.0001, 0.0005, 0.001)
STEPS = (1e-5, 5e-6)
TOL = dict(
    equilibrium_absolute=1e-7,
    matrix_relative=2e-7,
    analytic_difference_relative=2e-7,
    eigenpair_relative=1e-9,
    classification_per_s=1e-5,
)


def relative_error(actual, expected):
    return float(np.linalg.norm(actual - expected) / max(1.0, np.linalg.norm(expected)))


def independent_control(x, p, converter, variant):
    """Independent algebraic transcription; no internal-voltage input is used.

    Only the VI voltage-reference term changes. All capacitor/inductor omega
    cross-couplings continue to use the instantaneous frequency ratio.
    """
    if variant not in VARIANTS:
        raise ValueError(f"Unknown variant {variant}")
    omega = 1.0 + x[1]
    vi_omega = omega if variant == VARIANTS[0] else 1.0
    ic, vc, ig = x[4:6], x[6:8], x[8:10]
    vref = np.array(
        [
            converter.voltage_setpoint_pu
            + p.reactive_power_voltage_droop_pu
            * (converter.reactive_power_setpoint_pu - x[3]),
            0.0,
        ]
    )
    vref = (
        vref - p.virtual_resistance_pu * ig - p.virtual_reactance_pu * vi_omega * J @ ig
    )
    voltage_error = vref - vc
    iref = (
        ig
        + p.filter_capacitor_susceptance_pu * omega * J @ vc
        + p.voltage_proportional_gain_pu * voltage_error
        + x[10:12]
    )
    current_error = iref - ic
    command = (
        vc
        + p.converter_side_resistance_pu * ic
        + p.converter_side_reactance_pu * omega * J @ ic
        + p.current_proportional_gain_pu * current_error
        + x[12:14]
    )
    return voltage_error, current_error, command


def independent_command(x, p, converter, variant):
    return independent_control(x, p, converter, variant)[2]


def variant_rhs(x, model, variant):
    """Retain baseline network/physical/outer RHS; recompute affected channels.

    Unlike a direct A edit, this nonlinear definition retains the bilinear
    frequency-current mechanism and propagates it through all three channels.
    """
    p = model.parameters
    out = _closed_rhs(
        x,
        model.operating_point.grid_voltage_global,
        _references(model.converter),
        model.topology,
        p,
        model.converter,
        model.line,
    ).copy()
    ev, ei, command = independent_control(x[:14], p, model.converter, variant)
    out[10:12] = p.voltage_integral_gain_per_s * ev
    out[12:14] = p.current_integral_gain_per_s * ei
    out[14:16] = (command - x[14:16]) / p.modulation_time_constant_s
    return out


def jacobian(function, point, step):
    out = np.empty((len(function(point)), len(point)))
    for k in range(len(point)):
        h = step * max(1.0, abs(float(point[k])))
        plus, minus = point.copy(), point.copy()
        plus[k] += h
        minus[k] -= h
        out[:, k] = (function(plus) - function(minus)) / (2 * h)
    if not np.all(np.isfinite(out)):
        raise ValueError("Nonfinite Jacobian")
    return out


def analytic_difference(x, p):
    """Jacobian of fixed-minus-instantaneous nonlinear RHS, general state.

    Delta-vref=Xv*frequency_deviation*J*ig. At nominal equilibrium only
    column frequency remains, but it affects six controller derivatives.
    """
    dv = np.zeros((2, 16))
    dv[:, 1] = p.virtual_reactance_pu * J @ x[8:10]
    dv[:, 8:10] = p.virtual_reactance_pu * x[1] * J
    out = np.zeros((16, 16))
    out[10:12] = p.voltage_integral_gain_per_s * dv
    out[12:14] = p.current_integral_gain_per_s * p.voltage_proportional_gain_pu * dv
    out[14:16] = (
        p.current_proportional_gain_pu
        * p.voltage_proportional_gain_pu
        * dv
        / p.modulation_time_constant_s
    )
    return out


def spectrum(matrix, period=None):
    values, vectors = eig(matrix)
    scale = max(1.0, np.linalg.norm(matrix, 2))
    residual = max(
        float(
            np.linalg.norm(matrix @ vectors[:, k] - values[k] * vectors[:, k])
            / (scale * np.linalg.norm(vectors[:, k]))
        )
        for k in range(len(values))
    )
    radius = float(np.max(abs(values)))
    metric = (
        float(np.max(values.real)) if period is None else float(np.log(radius) / period)
    )
    label = (
        "numerical-pending"
        if residual > TOL["eigenpair_relative"]
        or abs(metric) <= TOL["classification_per_s"]
        else ("stable" if metric < 0 else "unstable")
    )
    order = np.lexsort((values.imag, values.real))
    return dict(
        spectrum=[[float(values[k].real), float(values[k].imag)] for k in order],
        root_count=len(values),
        metric_per_s=metric,
        metric_name="alpha" if period is None else "log_rho_over_Ts",
        spectral_radius=None if period is None else radius,
        maximum_eigenpair_relative_residual=residual,
        classification=label,
    )


def combine_steps(spectra):
    labels = [row["classification"] for row in spectra]
    return labels[0] if len(set(labels)) == 1 else "numerical-pending"


def compare_labels(labels):
    if "numerical-pending" in labels:
        return dict(
            comparison_status="numerical-pending", classification_disagreement=None
        )
    disagreement = len(set(labels)) != 1
    return dict(
        comparison_status="definite-disagreement"
        if disagreement
        else "definite-agreement",
        classification_disagreement=disagreement,
    )


def build_point(line_x, virtual_x, step=STEPS[0]):
    topology, p = build_average_dq_ablation_anchor_case()
    topology.lines[0].reactance_pu = line_x
    p = p.model_copy(update=dict(virtual_reactance_pu=virtual_x))
    return build_average_dq_model(topology, p, relative_step=step)


def main():
    started = time.perf_counter()
    output = ROOT / "results/virtual-reactance-frequency-pilot"
    plan = output / "plan.md"
    if not plan.is_file():
        raise RuntimeError("Pre-run plan must exist before execution")
    result = dict(
        schema="virtual-reactance-frequency-pilot/1.0",
        started_utc=datetime.now(timezone.utc).isoformat(),
        unique_change="Only algebraic VI voltage-reference frequency factor; all physical/filter omega terms retained.",
        hypothesis="The nominal-vs-instantaneous algebraic VI factor may change single-converter modal or sampled-command classifications on the fixed grid.",
        author_boundary="Author audit identifies dynamic Yv(s)=1/(s*Lv+Rv) and a coordinate-transform omega*Lv*J*i_ref term. These team algebraic variants neither correct an author omission nor validate two-machine relative update offsets.",
        configuration=dict(
            line_reactance_pu=LINE_X,
            virtual_reactance_pu=VIRTUAL_X,
            variants=VARIANTS,
            periods_s=PERIODS,
            delays_steps=[0, 1],
            holding_frame="local-control-dq",
            relative_steps=STEPS,
            voltage_pi_factor=1.0,
            current_pi_factor=1.0,
            P_pu=0.5,
            Q_pu=0.1,
            D=60,
        ),
        tolerances=TOL,
        points=[],
        sampled_records=[],
        classification_pairs=[],
        limitations=[
            "Team-defined single-converter average-value anchor, not author-model reproduction or hardware fitting.",
            "No two-machine interconnection or interaction mechanism validation.",
            "Only local-dq modulation envelope sampled; no physical abc hold, discrete PI, PWM, quantization or saturation.",
            "Original finite-Tmod continuous model is not the ideal instantaneous-command baseline. Removing Tmod can itself change stability; continuous-to-sampled disagreement alone cannot be attributed to sampling.",
            "Finite fixed grid; no theorem, continuous stability region, safe sampling recommendation or novelty established.",
            "Source hashes are provenance identifiers, not external integrity validation.",
        ],
        provenance=dict(
            python=sys.version,
            numpy=np.__version__,
            scipy=scipy.__version__,
            platform=platform.platform(),
            commit=subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
            ).strip(),
            command="python experiments/average-dq/run_virtual_reactance_frequency_pilot.py",
        ),
    )
    paths = [
        "backend/core/average_dq_model.py",
        "backend/core/average_dq_presets.py",
        "backend/domain/average_dq_models.py",
        "backend/domain/network_models.py",
        "backend/core/average_dq_sampled_command.py",
        "experiments/average-dq/run_virtual_reactance_frequency_pilot.py",
        "experiments/average-dq/test_virtual_reactance_frequency_pilot.py",
        "results/virtual-reactance-frequency-pilot/plan.md",
    ]
    result["provenance"]["source_sha256_provenance_only"] = {
        path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest() for path in paths
    }
    passed = True
    try:
        for line_x in LINE_X:
            for virtual_x in VIRTUAL_X:
                if time.perf_counter() - started > 90:
                    raise TimeoutError("90-second internal runtime budget exceeded")
                model = build_point(line_x, virtual_x)
                p, x = model.parameters, model.operating_point.state
                production_split = split_average_dq_sampled_command(
                    model, holding_frame="local-control-dq"
                )
                point = dict(
                    line_reactance_pu=line_x,
                    virtual_reactance_pu=virtual_x,
                    state=x.tolist(),
                    parameters=p.model_dump(mode="json"),
                    topology=model.topology.model_dump(mode="json"),
                    checks={},
                    variants={},
                )
                matrices = {}
                for variant in VARIANTS:
                    residual = float(np.max(abs(variant_rhs(x, model, variant))))
                    commands = independent_command(x[:14], p, model.converter, variant)
                    rows = []
                    for step in STEPS:
                        a = jacobian(
                            lambda candidate: variant_rhs(candidate, model, variant),
                            x,
                            step,
                        )
                        f = jacobian(
                            lambda candidate: independent_command(
                                candidate, p, model.converter, variant
                            ),
                            x[:14],
                            step,
                        )
                        a0, b = a[:14, :14], a[:14, 14:]
                        reconstructed = np.block(
                            [
                                [a0, b],
                                [
                                    f / p.modulation_time_constant_s,
                                    -np.eye(2) / p.modulation_time_constant_s,
                                ],
                            ]
                        )
                        rows.append(
                            dict(
                                relative_step=step,
                                closed_matrix=a.tolist(),
                                command_jacobian=f.tolist(),
                                split_reconstruction_relative=relative_error(
                                    reconstructed, a
                                ),
                                command_from_rhs_relative=relative_error(
                                    f, p.modulation_time_constant_s * a[14:, :14]
                                ),
                                continuous=spectrum(a),
                                ideal_command=spectrum(a0 + b @ f),
                            )
                        )
                        matrices[(variant, step)] = (a, a0, b, f)
                    point["variants"][variant] = dict(
                        equilibrium_max_abs_rhs=residual,
                        command_equilibrium_max_abs_error=float(
                            np.max(abs(commands - x[14:]))
                        ),
                        shared_equilibrium_state=True,
                        linearizations=rows,
                        continuous_classification=combine_steps(
                            [row["continuous"] for row in rows]
                        ),
                        ideal_command_classification=combine_steps(
                            [row["ideal_command"] for row in rows]
                        ),
                    )
                point["variant_comparisons"] = {}
                for mode in ("continuous", "ideal_command"):
                    labels = {
                        v: point["variants"][v][mode + "_classification"]
                        for v in VARIANTS
                    }
                    point["variant_comparisons"][mode] = dict(
                        classifications=labels,
                        **compare_labels(list(labels.values())),
                        metric_delta_fixed_minus_instantaneous=point["variants"][
                            VARIANTS[1]
                        ]["linearizations"][0][mode]["metric_per_s"]
                        - point["variants"][VARIANTS[0]]["linearizations"][0][mode][
                            "metric_per_s"
                        ],
                    )
                baseline = matrices[(VARIANTS[0], STEPS[0])]
                check = point["checks"]
                check["baseline_production_matrix_relative"] = relative_error(
                    baseline[0], model.linearization.closed_state_matrix
                )
                check["baseline_production_split_relative"] = max(
                    relative_error(baseline[1], production_split.a0),
                    relative_error(baseline[2], production_split.b),
                    relative_error(baseline[3], production_split.f),
                )
                check["two_step_matrix_relative_by_variant"] = {
                    v: relative_error(
                        matrices[(v, STEPS[1])][0], matrices[(v, STEPS[0])][0]
                    )
                    for v in VARIANTS
                }
                expected = analytic_difference(x, p)
                check["analytic_difference_relative_by_step"] = {
                    str(step): relative_error(
                        matrices[(VARIANTS[1], step)][0]
                        - matrices[(VARIANTS[0], step)][0],
                        expected,
                    )
                    for step in STEPS
                }
                check["analytic_difference_matrix"] = expected.tolist()
                check["same_equilibrium_rhs_difference_max_abs"] = float(
                    np.max(
                        abs(
                            variant_rhs(x, model, VARIANTS[1])
                            - variant_rhs(x, model, VARIANTS[0])
                        )
                    )
                )
                artificial = x.copy()
                artificial[1], artificial[8:10] = 0.03, 0.0
                check["zero_current_nonnominal_frequency_rhs_difference_max_abs"] = (
                    float(
                        np.max(
                            abs(
                                variant_rhs(artificial, model, VARIANTS[1])
                                - variant_rhs(artificial, model, VARIANTS[0])
                            )
                        )
                    )
                )
                artificial[1] = 0.0
                zero_diff = jacobian(
                    lambda z: (
                        variant_rhs(z, model, VARIANTS[1])
                        - variant_rhs(z, model, VARIANTS[0])
                    ),
                    artificial,
                    STEPS[0],
                )
                check["zero_current_nominal_frequency_difference_jacobian_max_abs"] = (
                    float(np.max(abs(zero_diff)))
                )
                check["Xv_zero_difference_matrix_max_abs"] = (
                    float(
                        np.max(abs(matrices[(VARIANTS[1], STEPS[0])][0] - baseline[0]))
                    )
                    if virtual_x == 0
                    else None
                )
                eq_errors = [
                    entry[k]
                    for entry in point["variants"].values()
                    for k in [
                        "equilibrium_max_abs_rhs",
                        "command_equilibrium_max_abs_error",
                    ]
                ]
                matrix_errors = [
                    check["baseline_production_matrix_relative"],
                    check["baseline_production_split_relative"],
                    *check["two_step_matrix_relative_by_variant"].values(),
                    *[
                        r[k]
                        for entry in point["variants"].values()
                        for r in entry["linearizations"]
                        for k in [
                            "split_reconstruction_relative",
                            "command_from_rhs_relative",
                        ]
                    ],
                ]
                check["passed"] = bool(
                    max(eq_errors) <= TOL["equilibrium_absolute"]
                    and max(matrix_errors) <= TOL["matrix_relative"]
                    and max(check["analytic_difference_relative_by_step"].values())
                    <= TOL["analytic_difference_relative"]
                    and check["same_equilibrium_rhs_difference_max_abs"]
                    <= TOL["equilibrium_absolute"]
                    and check[
                        "zero_current_nonnominal_frequency_rhs_difference_max_abs"
                    ]
                    <= TOL["equilibrium_absolute"]
                    and check[
                        "zero_current_nominal_frequency_difference_jacobian_max_abs"
                    ]
                    <= TOL["equilibrium_absolute"]
                    and (
                        virtual_x != 0
                        or check["Xv_zero_difference_matrix_max_abs"]
                        <= TOL["equilibrium_absolute"]
                    )
                )
                passed = passed and check["passed"]
                for period in PERIODS:
                    for delay in (0, 1):
                        pair = dict(
                            line_reactance_pu=line_x,
                            virtual_reactance_pu=virtual_x,
                            period_s=period,
                            delay_steps=delay,
                            classifications={},
                            metric_delta_fixed_minus_instantaneous=None,
                        )
                        metrics = {}
                        for variant in VARIANTS:
                            spectra = []
                            for step in STEPS:
                                _, a0, b, f = matrices[(variant, step)]
                                phi = sampled_command_matrices(
                                    a0, b, f, period, delay_steps=delay
                                ).phi
                                spectra.append(
                                    dict(relative_step=step, **spectrum(phi, period))
                                )
                            row = dict(
                                line_reactance_pu=line_x,
                                virtual_reactance_pu=virtual_x,
                                variant=variant,
                                period_s=period,
                                delay_steps=delay,
                                holding_frame="local-control-dq",
                                spectra_by_step=spectra,
                                classification=combine_steps(spectra),
                                two_step_metric_absolute_difference=abs(
                                    spectra[0]["metric_per_s"]
                                    - spectra[1]["metric_per_s"]
                                ),
                            )
                            result["sampled_records"].append(row)
                            pair["classifications"][variant] = row["classification"]
                            metrics[variant] = spectra[0]["metric_per_s"]
                        pair["metric_delta_fixed_minus_instantaneous"] = (
                            metrics[VARIANTS[1]] - metrics[VARIANTS[0]]
                        )
                        pair.update(
                            compare_labels(list(pair["classifications"].values()))
                        )
                        result["classification_pairs"].append(pair)
                result["points"].append(point)
                print(
                    f"X={line_x:g} Xv={virtual_x:g}: checks={check['passed']}",
                    flush=True,
                )
        result["summary"] = dict(
            point_count=len(result["points"]),
            sampled_record_count=len(result["sampled_records"]),
            pair_count=len(result["classification_pairs"]),
            classification_disagreement_count=sum(
                pair["classification_disagreement"] is True
                for pair in result["classification_pairs"]
            ),
            sampled_pair_comparison_counts={
                status: sum(
                    pair["comparison_status"] == status
                    for pair in result["classification_pairs"]
                )
                for status in [
                    "definite-agreement",
                    "definite-disagreement",
                    "numerical-pending",
                ]
            },
            classification_counts={
                label: sum(
                    row["classification"] == label for row in result["sampled_records"]
                )
                for label in ["stable", "unstable", "numerical-pending"]
            },
            continuous_classification_counts={
                label: sum(
                    entry["continuous_classification"] == label
                    for point in result["points"]
                    for entry in point["variants"].values()
                )
                for label in ["stable", "unstable", "numerical-pending"]
            },
            ideal_command_classification_counts={
                label: sum(
                    entry["ideal_command_classification"] == label
                    for point in result["points"]
                    for entry in point["variants"].values()
                )
                for label in ["stable", "unstable", "numerical-pending"]
            },
            VI_pair_comparison_counts_by_model={
                mode: {
                    status: sum(
                        point["variant_comparisons"][mode]["comparison_status"]
                        == status
                        for point in result["points"]
                    )
                    for status in [
                        "definite-agreement",
                        "definite-disagreement",
                        "numerical-pending",
                    ]
                }
                for mode in ["continuous", "ideal_command"]
            },
            sampling_attribution_boundary="All original finite-Tmod continuous models are stable but all ideal-command A0+B*F models are unstable on this grid. Therefore original-continuous versus sampled instability is not evidence that sampling caused the instability; removal of the modulation lag already changes the baseline.",
            interpretation="Observed finite-grid single-converter differences only; no stability improvement, author correction or two-machine contribution established.",
        )
        passed = passed and len(result["sampled_records"]) == 72
    except Exception as error:
        passed = False
        result["failure"] = dict(type=type(error).__name__, message=str(error))
    result["elapsed_seconds"] = time.perf_counter() - started
    result["passed"] = bool(passed and result["elapsed_seconds"] <= 90)
    output.mkdir(parents=True, exist_ok=True)
    target = output / "pilot.json"
    target.write_text(
        json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    reread = json.loads(target.read_text(encoding="utf-8"))
    if reread["passed"] != result["passed"] or len(reread["sampled_records"]) != len(
        result["sampled_records"]
    ):
        raise RuntimeError("Saved result verification failed")
    print(
        json.dumps(
            dict(
                passed=result["passed"],
                elapsed_seconds=result["elapsed_seconds"],
                summary=result.get("summary"),
                failure=result.get("failure"),
            ),
            ensure_ascii=False,
        )
    )
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
