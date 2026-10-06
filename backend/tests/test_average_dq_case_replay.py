"""Numerical replay of the versioned case input used by the web workbench.

This tests the existing average-dq solver, not a new stability method.
"""

import copy
import json
import math
import unittest

import numpy as np
from fastapi.testclient import TestClient

from backend.api.app import app
from backend.core.average_dq_presets import build_average_dq_verification_case


class AverageDQCaseReplayTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.client = TestClient(app)
        topology, parameters = build_average_dq_verification_case()
        cls.input = {
            "topology": topology.model_dump(mode="json"),
            "parameters": parameters.model_dump(mode="json"),
            "simulation_time_s": 0.05,
            "time_step_s": 0.005,
            "initial_angle_perturbation_rad": 0.000123456789,
            "frequency_values_hz": [0.2, 0.7, 2.0, 13.0],
        }
        saved = json.dumps(
            {"schema_version": "AverageDQCase/1.0", "input": cls.input},
            allow_nan=False,
        )
        cls.reloaded_input = json.loads(saved)["input"]
        cls.outputs = []
        for request in (cls.input, cls.reloaded_input):
            response = cls.client.post("/api/average-dq/analyze", json=request)
            if response.status_code != 200:
                raise AssertionError(response.text)
            cls.outputs.append(response.json())

    def test_saved_case_replays_the_same_complete_calculation(self) -> None:
        self.assertEqual(self.input, self.reloaded_input)
        first, replay = self.outputs
        self.assertEqual(first["input_topology"], replay["input_topology"])
        self.assertEqual(first["input_parameters"], replay["input_parameters"])
        self.assertEqual(first["result"]["stability"], replay["result"]["stability"])
        for key in ("closed_state_matrix", "poles", "port_admittance"):
            self.assertEqual(first["result"][key], replay["result"][key])
        np.testing.assert_allclose(
            first["operating_point"]["state"], replay["operating_point"]["state"],
            rtol=0.0, atol=1e-12,
        )
        for key in ("time_s", "nonlinear_states", "linear_states"):
            np.testing.assert_allclose(
                first["result"]["time_response"][key],
                replay["result"]["time_response"][key],
                rtol=0.0, atol=1e-12,
            )

    def test_nondefault_settings_reach_the_numerical_solver(self) -> None:
        result = self.outputs[0]
        response = result["result"]["time_response"]
        self.assertEqual(
            len(response["time_s"]),
            math.ceil(self.input["simulation_time_s"] / self.input["time_step_s"]) + 1,
        )
        self.assertEqual(response["time_s"][-1], self.input["simulation_time_s"])
        self.assertEqual(
            result["result"]["port_admittance"]["frequencies_hz"],
            self.input["frequency_values_hz"],
        )
        self.assertAlmostEqual(
            response["initial_state"][0] - result["operating_point"]["state"][0],
            self.input["initial_angle_perturbation_rad"], places=14,
        )

    def test_damping_edit_changes_the_actual_model_not_only_the_display(self) -> None:
        candidate = copy.deepcopy(self.reloaded_input)
        candidate["topology"]["grid_forming_converters"][0]["damping_coefficient_pu"] = 80.0
        response = self.client.post("/api/average-dq/analyze", json=candidate)
        self.assertEqual(response.status_code, 200, response.text)
        changed = response.json()
        self.assertEqual(
            changed["input_topology"]["grid_forming_converters"][0]["damping_coefficient_pu"],
            80.0,
        )
        self.assertFalse(np.allclose(
            self.outputs[0]["result"]["closed_state_matrix"],
            changed["result"]["closed_state_matrix"], rtol=0.0, atol=1e-12,
        ))
        self.assertNotEqual(self.outputs[0]["result"]["poles"], changed["result"]["poles"])
        self.assertEqual(self.input["topology"]["grid_forming_converters"][0]["damping_coefficient_pu"], 60.0)


if __name__ == "__main__":
    unittest.main()
