"""Independent rebuild of the stored single-converter VI pilot.

Uses the production baseline plus the explicitly derived rank-one VI change,
NumPy eigenvalues, and a freshly reconstructed period map. This is an
implementation check, not an independent physical model or novelty proof.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import numpy as np
from scipy.linalg import expm
from scipy.optimize import linear_sum_assignment

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
# Direct script execution needs the repository root before project imports.
from backend.core.average_dq_model import build_average_dq_model  # noqa: E402
from backend.domain.average_dq_models import AverageDQGFMParameters  # noqa: E402
from backend.domain.network_models import NetworkTopology  # noqa: E402


def spectrum_error(expected, stored):
    actual = np.asarray(stored, dtype=float)
    actual = actual[:, 0] + 1j * actual[:, 1]
    assert len(expected) == len(actual), "Incomplete spectrum"
    distance = abs(expected[:, None] - actual[None, :])
    row, column = linear_sum_assignment(distance)
    return float(np.max(distance[row, column]))


def classify(metric):
    return (
        "numerical-pending"
        if abs(metric) <= 1e-5
        else ("stable" if metric < 0 else "unstable")
    )


def main():
    source = ROOT / "results/virtual-reactance-frequency-pilot/pilot.json"
    data = json.loads(source.read_text(encoding="utf-8"))
    assert data["passed"]
    assert len(data["points"]) == 6
    assert len(data["sampled_records"]) == 72
    assert len(data["classification_pairs"]) == 36
    for name, expected in data["provenance"]["source_sha256_provenance_only"].items():
        observed = hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
        assert observed == expected, f"Local source snapshot changed: {name}"

    records = {}
    for record in data["sampled_records"]:
        key = (
            record["line_reactance_pu"],
            record["virtual_reactance_pu"],
            record["variant"],
            record["period_s"],
            record["delay_steps"],
        )
        assert key not in records, "Duplicate configuration"
        records[key] = record
    max_matrix_error = max_root_error = max_metric_error = 0.0
    counts = {"continuous": {}, "ideal_command": {}, "sampled": {}}
    for point in data["points"]:
        topology = NetworkTopology.model_validate(point["topology"])
        parameters = AverageDQGFMParameters.model_validate(point["parameters"])
        assert topology.lines[0].reactance_pu == point["line_reactance_pu"]
        assert parameters.virtual_reactance_pu == point["virtual_reactance_pu"]
        for step in (1e-5, 5e-6):
            model = build_average_dq_model(topology, parameters, relative_step=step)
            x = model.operating_point.state
            np.testing.assert_allclose(x, point["state"], atol=1e-10, rtol=1e-10)
            assert abs(x[1]) < 1e-12
            # J*i = [-i_q, i_d]. Only the VI term is frozen; plant and
            # capacitor/inductor feedforward frequency terms stay unchanged.
            voltage_change = parameters.virtual_reactance_pu * np.array([-x[9], x[8]])
            change = np.zeros((16, 16))
            change[10:12, 1] = parameters.voltage_integral_gain_per_s * voltage_change
            change[12:14, 1] = (
                parameters.current_integral_gain_per_s
                * parameters.voltage_proportional_gain_pu
                * voltage_change
            )
            change[14:16, 1] = (
                parameters.current_proportional_gain_pu
                * parameters.voltage_proportional_gain_pu
                * voltage_change
                / parameters.modulation_time_constant_s
            )
            for variant in ("instantaneous-frequency", "fixed-nominal-frequency"):
                a = model.linearization.closed_state_matrix.copy()
                if variant == "fixed-nominal-frequency":
                    a += change
                saved = next(
                    row
                    for row in point["variants"][variant]["linearizations"]
                    if row["relative_step"] == step
                )
                error = float(
                    np.linalg.norm(a - np.array(saved["closed_matrix"]))
                    / max(1.0, np.linalg.norm(a))
                )
                max_matrix_error = max(max_matrix_error, error)
                assert error < 2e-7
                a0, b = a[:14, :14], a[:14, 14:]
                f = parameters.modulation_time_constant_s * a[14:, :14]
                for kind, matrix in (("continuous", a), ("ideal_command", a0 + b @ f)):
                    roots = np.linalg.eigvals(matrix)
                    root_error = spectrum_error(roots, saved[kind]["spectrum"])
                    assert root_error < 2e-5
                    max_root_error = max(max_root_error, root_error)
                    metric = float(max(roots.real))
                    max_metric_error = max(
                        max_metric_error, abs(metric - saved[kind]["metric_per_s"])
                    )
                    assert classify(metric) == saved[kind]["classification"]
                    if step == 1e-5:
                        label = classify(metric)
                        counts[kind][label] = counts[kind].get(label, 0) + 1
                for period in (0.0001, 0.0005, 0.001):
                    block = np.zeros((16, 16))
                    block[:14, :14], block[:14, 14:] = a0, b
                    transition = expm(period * block)
                    e, g = transition[:14, :14], transition[:14, 14:]
                    for delay in (0, 1):
                        phi = (
                            e + g @ f
                            if delay == 0
                            else np.block([[e, g], [f, np.zeros((2, 2))]])
                        )
                        key = (
                            point["line_reactance_pu"],
                            point["virtual_reactance_pu"],
                            variant,
                            period,
                            delay,
                        )
                        record = records[key]
                        saved_spectrum = next(
                            row
                            for row in record["spectra_by_step"]
                            if row["relative_step"] == step
                        )
                        assert saved_spectrum["root_count"] == (
                            14 if delay == 0 else 16
                        )
                        roots = np.linalg.eigvals(phi)
                        root_error = spectrum_error(roots, saved_spectrum["spectrum"])
                        assert root_error < 2e-7
                        max_root_error = max(max_root_error, root_error)
                        metric = float(np.log(max(abs(roots))) / period)
                        metric_error = abs(metric - saved_spectrum["metric_per_s"])
                        assert metric_error < 2e-5
                        max_metric_error = max(max_metric_error, metric_error)
                        assert classify(metric) == record["classification"]
                        if step == 1e-5:
                            label = classify(metric)
                            counts["sampled"][label] = (
                                counts["sampled"].get(label, 0) + 1
                            )
    assert counts == {
        "continuous": {"stable": 12},
        "ideal_command": {"unstable": 12},
        "sampled": {"unstable": 66, "stable": 6},
    }, counts
    assert data["summary"]["classification_disagreement_count"] == 0
    report = dict(
        passed=True,
        point_count=6,
        sampled_records=72,
        rebuilt_steps=[1e-5, 5e-6],
        classification_counts=counts,
        maximum_matrix_relative_error=max_matrix_error,
        maximum_matched_spectrum_absolute_error=max_root_error,
        maximum_metric_absolute_error_per_s=max_metric_error,
        pilot_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
        verifier_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        limitation="Independent analytic reconstruction and numerical recomputation; same production physical model, not physical validation.",
    )
    target = source.with_name("verification.json")
    target.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    assert json.loads(target.read_text(encoding="utf-8")) == report
    print(json.dumps(report))


if __name__ == "__main__":
    main()
