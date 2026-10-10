"""Read-only frozen-oracle verification of the migrated sampled-command kernel.

Only the verification result is written. The original holdout and source
manifest are pinned by hashes recorded before kernel implementation.
"""

from __future__ import annotations

import hashlib
import itertools
import json
import sys
import time
from pathlib import Path

import numpy as np
from scipy.optimize import linear_sum_assignment

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
EXPECTED_PATH = ROOT / "results/average-dq-sampled-modulation-holdout/holdout.json"
OUTPUT_PATH = ROOT / "results/verification/sampled-command-kernel-2026-10-02.json"
EXPECTED_SHA256 = "0ad548061dce8340366d7589b55cd8c6e6609344d7bea25591e560dffea928a7"
SOURCE_MANIFEST = {
    "experiments/average-dq/run_sampled_modulation_holdout.py": "3904c89fc18d0e81216fddbf91e30d4f2c33923819a43f49e09154b353095c2c",
    "experiments/average-dq/run_sampled_modulation_pilot.py": "731b2758125abf00b43e56373ddb07d3cf575425429446ac2b47c59c0141b71f",
    "backend/core/average_dq_model.py": "cb936f5c2249d268d4a0422eea23c0da8b7e1f969c388bfee082c7493e34b875",
    "backend/core/average_dq_presets.py": "365aabca397a7d96cd41ae8157ae08dc9722c207b8eb0c263213c4dae211737f",
}
X_VALUES = (0.2, 0.4)
PI_FACTORS = (0.5, 1.0, 1.5, 2.0, 3.0, 4.0)
PERIODS = (1e-4, 5e-4, 1e-3, 2e-3)
HOLDS = ("local-control-dq", "global-synchronous-dq")
DELAYS = (0, 1)
EXPECTED_ASSUMPTIONS = (
    "Experimental opt-in analysis of one declared 16-state average-value model.",
    "Only the modulation command envelope is sampled; PI, outer loops, filters and phase synthesis remain continuous.",
    "Local-control dq hold is not physical alpha-beta/abc hold; global-synchronous dq is also not a PWM implementation.",
    "Global held buffer uses equilibrium-aligned axes q=R(-delta*)*Delta(v_global).",
    "One-step delay applies the old complete held command snapshot and queues the current snapshot for the next cycle.",
    "Zero-order hold integration is exact for the declared linear plant under a constant input, not for digital hardware.",
    "The same-hold first-order lag tau=(delay_steps+0.5)*Ts is a low-frequency approximation, not an equivalent physical actuator.",
    "Stability labels use the complete spectrum, including two buffer modes for one-step delay.",
    "Numerical pending thresholds and step differences are diagnostics, not guaranteed eigenvalue error bounds.",
    "No switching, saturation, quantization, multirate execution, EMT or physical confirmation; no safe sampling-period prescription.",
    "Novelty has not been established; matrix exponential and sampled-feedback methods are existing methods.",
)
SPECTRUM_RELATIVE_TOLERANCE = 1e-7
METRIC_ABSOLUTE_TOLERANCE_PER_S = 1e-5
START = 0.0


def deadline():
    if time.perf_counter() - START > 115:
        raise TimeoutError("Verification exceeded its internal 115-second deadline")


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def identity_check(expected):
    actual_json_hash = sha256(EXPECTED_PATH)
    require(
        actual_json_hash == EXPECTED_SHA256, "Frozen expected JSON identity changed"
    )
    stored = {
        name.replace("\\", "/"): value
        for name, value in expected["provenance"][
            "source_sha256_provenance_only"
        ].items()
    }
    require(stored == SOURCE_MANIFEST, "Frozen expected source manifest changed")
    actual_sources = {name: sha256(ROOT / name) for name in SOURCE_MANIFEST}
    require(actual_sources == SOURCE_MANIFEST, "Original source identity changed")
    return {
        "expected_json_sha256": actual_json_hash,
        "original_sources_sha256": actual_sources,
        "actual_matches_pinned_expected": True,
    }


def record_key(row):
    return (
        float(row["X_pu"]),
        float(row["current_pi_factor"]),
        float(row["period_s"]),
        row["hold"],
        int(row["delay_steps"]),
    )


def complex_spectrum(pairs):
    array = np.asarray(pairs, dtype=float)
    require(
        array.ndim == 2 and array.shape[1] == 2 and np.isfinite(array).all(),
        "Spectrum must be finite real/imaginary pairs",
    )
    return array[:, 0] + 1j * array[:, 1]


def compare_spectrum(actual, expected, label):
    a, e = complex_spectrum(actual), complex_spectrum(expected)
    require(len(a) == len(e), f"{label}: spectrum order changed")
    costs = np.abs(a[:, None] - e[None, :]) / np.maximum(1.0, np.abs(e))[None, :]
    rows, columns = linear_sum_assignment(costs)
    maximum = float(np.max(costs[rows, columns]))
    require(
        maximum <= SPECTRUM_RELATIVE_TOLERANCE,
        f"{label}: Hungarian spectrum relative error {maximum} exceeds tolerance",
    )
    return maximum


def compare_analysis(actual, expected, label):
    spectral_error = compare_spectrum(actual["spectrum"], expected["spectrum"], label)
    require(
        actual["metric_name"] in ("alpha", "log_rho_over_Ts"),
        f"{label}: unknown metric",
    )
    require(
        np.isfinite(actual["maximum_eigenpair_relative_residual"])
        and actual["maximum_eigenpair_relative_residual"] <= 1e-9,
        f"{label}: eigenpair residual violates frozen gate",
    )
    error = abs(float(actual["metric_per_s"]) - float(expected["metric_per_s"]))
    require(
        np.isfinite(error) and error <= METRIC_ABSOLUTE_TOLERANCE_PER_S,
        f"{label}: growth-rate error {error} exceeds tolerance",
    )
    require(
        actual["classification"] == expected["classification"],
        f"{label}: classification changed",
    )
    require(
        actual["metric_name"] == expected["metric_name"],
        f"{label}: metric meaning changed",
    )
    return {
        "maximum_matched_spectrum_relative_error": spectral_error,
        "metric_absolute_error_per_s": error,
        "classification_matches": True,
        "order": len(actual["spectrum"]),
    }


def category_summary(rows):
    index = {record_key(row): row for row in rows}
    summaries = []
    for hold, delay in itertools.product(HOLDS, DELAYS):
        subset = [
            row for row in rows if row["hold"] == hold and row["delay_steps"] == delay
        ]
        summaries.append(
            {
                "hold": hold,
                "delay_steps": delay,
                "paired_comparisons": len(subset),
                "disagreement_count": sum(row["label_disagreement"] for row in subset),
            }
        )
    coordinate_differences = delay_differences = coordinate_pairs = delay_pairs = 0
    for x, factor, period in itertools.product(X_VALUES, PI_FACTORS, PERIODS):
        for delay in DELAYS:
            left, right = (index[(x, factor, period, hold, delay)] for hold in HOLDS)
            coordinate_pairs += 1
            coordinate_differences += (
                left["sampled"]["classification"] != right["sampled"]["classification"]
            )
        for hold in HOLDS:
            left, right = (index[(x, factor, period, hold, delay)] for delay in DELAYS)
            delay_pairs += 1
            delay_differences += (
                left["sampled"]["classification"] != right["sampled"]["classification"]
            )
    return {
        "by_hold_delay": summaries,
        "coordinate_comparison": {
            "pairs": coordinate_pairs,
            "label_differences": coordinate_differences,
        },
        "delay_comparison": {
            "pairs": delay_pairs,
            "label_differences": delay_differences,
        },
    }


def main():
    global START
    START = time.perf_counter()
    result = {
        "schema": "sampled-command-kernel-verification/1.0",
        "date": "2026-10-02",
        "status": "failed",
        "comparison_coverage": 0,
        "tolerances": {
            "maximum_matched_spectrum_relative": SPECTRUM_RELATIVE_TOLERANCE,
            "metric_absolute_per_s": METRIC_ABSOLUTE_TOLERANCE_PER_S,
        },
        "rows": [],
        "limitations": [
            "Numerical migration equivalence only, not new physical or nonlinear validation.",
            "Frozen deterministic model comparisons are not independent trials.",
        ],
    }
    try:
        expected = json.loads(EXPECTED_PATH.read_text(encoding="utf-8"))
        result["identity_before"] = identity_check(expected)
        require(
            expected["status"] == "verified-bounded-holdout",
            "Expected holdout was not verified",
        )
        expected_rows = expected["records"]
        keys = [record_key(row) for row in expected_rows]
        prescribed = set(
            itertools.product(X_VALUES, PI_FACTORS, PERIODS, HOLDS, DELAYS)
        )
        require(
            len(keys) == 192 and len(set(keys)) == 192 and set(keys) == prescribed,
            "Expected records do not cover exactly 192 unique prescribed keys",
        )
        # New-kernel imports and calculations are deliberately isolated below;
        # no old holdout implementation or old expected labels supply outputs.
        new_kernel_before = sha256(ROOT / "backend/core/average_dq_sampled_command.py")
        calculated = calculate_records()
        actual_keys = [record_key(row) for row in calculated]
        require(
            len(actual_keys) == 192
            and len(set(actual_keys)) == 192
            and set(actual_keys) == prescribed,
            "New kernel does not cover exactly 192 unique prescribed keys",
        )
        expected_index = {record_key(row): row for row in expected_rows}
        for actual in calculated:
            deadline()
            key = record_key(actual)
            oracle = expected_index[key]
            require(
                actual["phase_matched_tau_s"] == oracle["phase_matched_tau_s"],
                f"{key}: lag time constant changed",
            )
            require(
                actual["D_pu"] == 60 and actual["R_pu"] == oracle["R_pu"],
                f"{key}: operating assumptions changed",
            )
            require(
                actual["coordinate_input_basis"] == oracle["coordinate_input_basis"],
                f"{key}: canonical input basis changed",
            )
            comparisons = {
                kind: compare_analysis(actual[kind], oracle[kind], f"{key} {kind}")
                for kind in ("sampled", "lag", "ideal")
            }
            for kind in ("sampled", "lag", "ideal"):
                roots = complex_spectrum(actual[kind]["spectrum"])
                inferred_metric = (
                    float(np.log(np.max(np.abs(roots))) / key[2])
                    if kind == "sampled"
                    else float(np.max(roots.real))
                )
                require(
                    abs(inferred_metric - actual[kind]["metric_per_s"])
                    <= METRIC_ABSOLUTE_TOLERANCE_PER_S,
                    f"{key} {kind}: metric is inconsistent with freshly computed full spectrum",
                )
            require(
                comparisons["sampled"]["order"] == (14 if key[4] == 0 else 16),
                f"{key}: sampled delay order incorrect",
            )
            require(
                comparisons["lag"]["order"] == 16
                and comparisons["ideal"]["order"] == 14,
                f"{key}: comparator order incorrect",
            )
            require(
                actual["label_disagreement"] == oracle["label_disagreement"],
                f"{key}: paired classification disagreement changed",
            )
            result["rows"].append(
                {
                    "key": list(key),
                    "comparisons": comparisons,
                    "lag_tau_s": actual["phase_matched_tau_s"],
                    "metadata_matches": True,
                    "new_core_step_check": actual["core_metadata"]["step_check"],
                    "assumptions_match_reviewed_contract": True,
                }
            )
            result["comparison_coverage"] += 1
        categories = category_summary(calculated)
        require(
            categories["by_hold_delay"] == expected["summary_by_hold_delay"],
            "Hold/delay categories changed",
        )
        require(
            categories["coordinate_comparison"]
            == expected["coordinate_label_comparison"],
            "Coordinate comparison changed",
        )
        require(
            categories["delay_comparison"] == expected["delay_label_comparison"],
            "Delay comparison changed",
        )
        require(
            categories["coordinate_comparison"]["label_differences"] == 0
            and categories["delay_comparison"]["label_differences"] == 38,
            "Frozen coordinate/delay negative and positive findings changed",
        )
        result["categories"] = categories
        result["verified_core_assumptions"] = list(EXPECTED_ASSUMPTIONS)
        result["fresh_operating_points"] = 12
        result["fresh_linearizations"] = 24
        result["identity_after"] = identity_check(expected)
        require(
            sha256(ROOT / "backend/core/average_dq_sampled_command.py")
            == new_kernel_before,
            "New kernel source changed during verification",
        )
        result["provenance"] = {
            "verifier_sha256": sha256(Path(__file__)),
            "new_kernel_sha256": new_kernel_before,
        }
        result["status"] = "passed-frozen-192-record-migration"
    except Exception as error:
        result["error"] = f"{type(error).__name__}: {error}"
    result["runtime_s"] = time.perf_counter() - START
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                key: result[key]
                for key in ("status", "comparison_coverage", "runtime_s")
            },
            ensure_ascii=False,
        )
    )
    if "error" in result:
        print(result["error"], file=sys.stderr)
    return 0 if result["status"] == "passed-frozen-192-record-migration" else 1


def calculate_records():
    from backend.core.average_dq_model import build_average_dq_model, STATE_LABELS
    from backend.core.average_dq_presets import build_average_dq_ablation_anchor_case
    from backend.core.average_dq_sampled_command import (
        compare_average_dq_sampled_command,
    )

    calculated = []
    reference_mapping = {
        "sampled": "sampled_command",
        "lag": "same_hold_low_frequency_lag",
        "ideal": "ideal_instantaneous",
    }
    for x, factor in itertools.product(X_VALUES, PI_FACTORS):
        deadline()
        topology, parameters = build_average_dq_ablation_anchor_case()
        next(line for line in topology.lines if line.id == "line-grid").reactance_pu = x
        parameters = parameters.model_copy(
            update={
                "current_proportional_gain_pu": parameters.current_proportional_gain_pu
                * factor,
                "current_integral_gain_per_s": parameters.current_integral_gain_per_s
                * factor,
            }
        )
        model = build_average_dq_model(topology, parameters, relative_step=1e-5)
        half = build_average_dq_model(topology, parameters, relative_step=5e-6)
        require(
            model.line.reactance_pu == x
            and model.line.resistance_pu == 0.02
            and model.converter.damping_coefficient_pu == 60,
            "Fresh model does not match fixed line/damping assumptions",
        )
        for hold, delay, period in itertools.product(HOLDS, DELAYS, PERIODS):
            deadline()
            fresh = compare_average_dq_sampled_command(
                model,
                period,
                holding_frame=hold,
                delay_steps=delay,
                comparison_model=half,
                state_labels=STATE_LABELS,
            )
            require(
                fresh["experimental"] is True
                and fresh["sampling_period_s"] == period
                and fresh["holding_frame"] == hold
                and fresh["delay_steps"] == delay,
                "Core comparison changed execution assumptions",
            )
            require(
                tuple(fresh["assumptions"]) == EXPECTED_ASSUMPTIONS,
                "Core assumptions differ from the independently reviewed contract",
            )
            require(
                fresh["theorem_status"] == "not-evaluated-by-sampled-api"
                and fresh["physical_validation_status"] == "not-performed",
                "Core comparison makes unsupported theorem or physical claims",
            )
            require(
                fresh["benchmark_coverage"] == "within-tested-period-range-only",
                "Core period coverage declaration changed",
            )
            require(
                tuple(fresh["original_state_labels"]) == tuple(STATE_LABELS)
                and fresh["state_dimension"] == (14 if delay == 0 else 16),
                "Core state order or delay dimension changed",
            )
            require(
                fresh["step_check"]["status"] == "step-comparison-evaluated"
                and fresh["step_check"]["primary_relative_step"] == 1e-5
                and fresh["step_check"]["comparison_relative_step"] == 5e-6,
                "Core did not compare the independently built two linearization steps",
            )
            buffer = (
                "none"
                if delay == 0
                else "previous complete held command in the declared holding frame; global buffer equilibrium-aligned"
            )
            require(
                fresh["sampled_buffer_definition"] == buffer,
                "Core command-cache convention changed",
            )
            require(
                fresh["limits"]
                == {
                    "tiny_period_pending_s": 1e-8,
                    "label_tolerance_per_s": 1e-5,
                    "eigenpair_residual_tolerance": 1e-9,
                    "step_difference_multiplier": 10,
                },
                "Core diagnostic gates changed",
            )
            analyses = {
                name: fresh["references"][core_name]
                for name, core_name in reference_mapping.items()
            }
            for name, analysis in analyses.items():
                expected_labels = list(STATE_LABELS[:14])
                if name == "sampled" and delay == 1:
                    expected_labels += [
                        "previous_held_command_d_pu",
                        "previous_held_command_q_pu",
                    ]
                elif name == "lag":
                    expected_labels += [
                        "same_hold_lag_command_d_pu",
                        "same_hold_lag_command_q_pu",
                    ]
                require(
                    analysis["step_check_status"] == "step-comparison-evaluated"
                    and analysis["metric_units"] == "s^-1"
                    and analysis["dimension"] == len(analysis["spectrum"]),
                    "Core analysis lost step coverage, units, or full spectrum",
                )
                require(
                    analysis["name"] == reference_mapping[name]
                    and analysis["state_labels"] == expected_labels,
                    "Core analysis state order or reference meaning changed",
                )
            labels = [analyses[name]["classification"] for name in ("sampled", "lag")]
            calculated.append(
                {
                    "X_pu": x,
                    "D_pu": model.converter.damping_coefficient_pu,
                    "R_pu": model.line.resistance_pu,
                    "current_pi_factor": factor,
                    "period_s": fresh["sampling_period_s"],
                    "hold": fresh["holding_frame"],
                    "delay_steps": fresh["delay_steps"],
                    "phase_matched_tau_s": fresh["phase_matched_tau_s"],
                    **analyses,
                    "label_disagreement": labels[0] != labels[1]
                    and "numerical-pending" not in labels,
                    "coordinate_input_basis": "equilibrium local axes for both holdings",
                    "core_metadata": {"step_check": fresh["step_check"]},
                }
            )
    return calculated


if __name__ == "__main__":
    raise SystemExit(main())
