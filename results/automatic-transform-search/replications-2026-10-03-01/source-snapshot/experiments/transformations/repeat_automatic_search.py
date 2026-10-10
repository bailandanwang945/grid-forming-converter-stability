"""Seed replication using the unchanged candidate evaluator, not a new method."""
import argparse
import time
from pathlib import Path

import numpy as np

from automatic_search import (BASELINE, Candidate, Evaluator, hashes, mutate,
                              random_candidate, write_json)


def run(output):
    output.mkdir(parents=True, exist_ok=False)
    initial_hashes = hashes()
    initial_hashes["experiments/transformations/repeat_automatic_search.py"] = __import__("hashlib").sha256(Path(__file__).read_bytes()).hexdigest()
    evaluator = Evaluator()
    n = len(evaluator.cases["fig8_D_0p5"]["frequencies_hz"])
    development = np.unique(np.linspace(0, n - 1, 80).astype(int))
    holdout = np.setdiff1d(np.arange(n), development)
    start = time.monotonic()
    deadline = start + 180
    result = {"status": "running", "source_hashes": initial_hashes,
              "seeds": [20261005, 20261006, 20261007], "runs": [],
              "scope": "additional exploratory seed replications; not statistical confirmation"}
    base_candidate = Candidate(*BASELINE)
    baseline = evaluator.evaluate(base_candidate, "fig8_D_0p5", development)
    baseline_full = evaluator.evaluate(base_candidate, "fig8_D_0p5", np.arange(n))
    result["baseline_full_score"] = baseline_full["score"]

    def check_deadline():
        if time.monotonic() > deadline:
            raise TimeoutError("Replication exceeded 180-second budget")
        current = hashes()
        if any(current[key] != value for key, value in initial_hashes.items() if key in current):
            raise RuntimeError("Frozen evaluation inputs changed")

    try:
        for seed in result["seeds"]:
            rng = np.random.default_rng(seed)
            run_record = {"seed": seed, "records": [], "selected": {}}
            result["runs"].append(run_record)

            def evaluate(candidate, strategy):
                check_deadline()
                metrics = evaluator.evaluate(candidate, "fig8_D_0p5", development)
                record = {"strategy": strategy, "candidate": candidate.__dict__, "metrics": metrics}
                run_record["records"].append(record)
                write_json(output / "replications.json", result)
                print(f"seed={seed} candidate={len(run_record['records'])} status={metrics['status']}", flush=True)
                return record

            base_record = {"candidate": base_candidate.__dict__, "metrics": baseline}
            population = [base_record]
            population.extend(evaluate(random_candidate(rng), "evolution") for _ in range(6))
            for _ in range(3):
                leaders = sorted(population, key=lambda r: r["metrics"]["score"], reverse=True)[:3]
                for j in range(6):
                    parent = Candidate(**leaders[j % 3]["candidate"])
                    population.append(evaluate(mutate(parent, rng), "evolution"))
            random_rng = np.random.default_rng(seed + 1)
            random_records = [base_record] + [evaluate(random_candidate(random_rng), "random") for _ in range(24)]
            for strategy, records in [("evolution", population), ("random", random_records)]:
                check_deadline()
                selected = max(records, key=lambda r: r["metrics"]["score"])
                candidate = Candidate(**selected["candidate"])
                cases = {}
                for case_id in evaluator.cases:
                    check_deadline()
                    full = evaluator.evaluate(candidate, case_id, np.arange(n))
                    full["holdout_minimum_margin"] = float(np.min(np.asarray(full["normalized_mixed_margin"])[holdout]))
                    cases[case_id] = full
                run_record["selected"][strategy] = {"candidate": candidate.__dict__, "cases": cases}
            write_json(output / "replications.json", result)
        check_deadline()
        result.update(status="complete", elapsed_seconds=time.monotonic() - start)
        write_json(output / "replications.json", result)
        print(f"REPLICATIONS_COMPLETE {output}", flush=True)
    except Exception as exc:
        result.update(status="incomplete", error=f"{type(exc).__name__}: {exc}")
        write_json(output / "replications.json", result)
        raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    run(parser.parse_args().output)
