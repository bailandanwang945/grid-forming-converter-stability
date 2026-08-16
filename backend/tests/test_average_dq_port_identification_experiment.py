from __future__ import annotations

import csv
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
ENTRYPOINT = (
    PROJECT_ROOT
    / "experiments"
    / "average-dq"
    / "run_port_sinestream_identification.py"
)


def _load_entrypoint():
    specification = importlib.util.spec_from_file_location(
        "average_dq_port_identification_experiment", ENTRYPOINT
    )
    if specification is None or specification.loader is None:
        raise RuntimeError(f"无法载入实验入口：{ENTRYPOINT}")
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


class AverageDQPortIdentificationExperimentTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.module = _load_entrypoint()
        cls.temporary_directory = tempfile.TemporaryDirectory()
        cls.output_dir = Path(cls.temporary_directory.name)
        cls.json_path, cls.csv_path = cls.module.run_experiment(cls.output_dir)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temporary_directory.cleanup()

    def test_artifacts_keep_fixed_contract_and_complete_matrix_rows(self) -> None:
        self.assertEqual(
            self.json_path.name, "port_sinestream_identification.json"
        )
        self.assertEqual(
            self.csv_path.name,
            "port_sinestream_identification_elements.csv",
        )
        payload = json.loads(self.json_path.read_text(encoding="utf-8"))
        self.assertTrue(payload["summary"]["passed"])
        self.assertEqual(payload["contract"]["frequencies_hz"], [0.2, 2.0, 20.0])
        self.assertEqual(payload["contract"]["source_amplitude_pu"], 1.0e-4)
        with self.csv_path.open(encoding="utf-8", newline="") as stream:
            rows = list(csv.DictReader(stream))
        self.assertEqual(len(rows), 12)
        self.assertEqual(
            {(float(row["frequency_hz"]), row["row"], row["column"]) for row in rows},
            {
                (frequency, str(row), str(column))
                for frequency in (0.2, 2.0, 20.0)
                for row in range(2)
                for column in range(2)
            },
        )

    def test_json_preserves_failure_gates_amplitude_check_and_scope(self) -> None:
        payload = json.loads(
            self.json_path.read_text(encoding="utf-8"),
            parse_constant=lambda value: self.fail(f"非法 JSON 数值：{value}"),
        )
        self.assertEqual(payload["contract"]["magnitude_error_limit"], 0.01)
        self.assertEqual(payload["contract"]["phase_error_limit_deg"], 1.0)
        self.assertLess(
            payload["amplitude_halving_check_at_2hz"][
                "maximum_element_relative_difference"
            ],
            1.0e-3,
        )
        self.assertGreater(
            payload["provenance"][
                "device_open_port_spectral_abscissa_per_s"
            ],
            0.0,
        )
        self.assertFalse(payload["model_scope"]["physical_validation"])
        self.assertFalse(payload["model_scope"]["emt_validation"])


if __name__ == "__main__":
    unittest.main()
