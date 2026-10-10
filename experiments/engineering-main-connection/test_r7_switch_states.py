"""Regression checks for R7 ideal-switch contraction and explicit assumptions."""

from __future__ import annotations

import copy
import json
import unittest

from check_r7_switch_states import (
    DEFAULT_SOURCE,
    DEVICE_KINDS,
    SWITCH_KINDS,
    ConnectivityInputError,
    compile_connectivity,
    teaching_scenarios,
)


class R7SwitchConnectivityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.source_bytes = DEFAULT_SOURCE.read_bytes()
        self.draft = json.loads(self.source_bytes)
        self.scenarios = teaching_scenarios(self.draft)
        self.switches = {
            c["component_id"]: True
            for c in self.draft["components"]
            if c["kind"] in SWITCH_KINDS
        }
        self.devices = {
            c["component_id"]: True
            for c in self.draft["components"]
            if c["kind"] in DEVICE_KINDS
        }
        self.provenance = {"origin": "explicit-teaching-assumption"}

    def compile_teaching(
        self, draft=None, switches=None, devices=None, provenance=None
    ):
        return compile_connectivity(
            self.draft if draft is None else draft,
            switch_overrides=self.switches if switches is None else switches,
            device_overrides=self.devices if devices is None else devices,
            state_source=self.provenance if provenance is None else provenance,
        )

    def test_all_closed_merges_bus_sections_but_not_transformer_or_line(self):
        result = self.scenarios["all_switches_closed"]
        mapping = result["engineering_node_to_calculation_node"]
        self.assertEqual(mapping["n-220-I"], mapping["n-220-II"])
        self.assertNotEqual(mapping["n-10p5-I"], mapping["n-T1-hv"])
        self.assertNotEqual(mapping["n-L1-local"], mapping["n-L1-external"])
        self.assertEqual(result["summary"]["equipotential_node_count"], 3)
        self.assertEqual(result["summary"]["topological_region_count"], 1)

    def test_section_breaker_open_separates_bus_sections(self):
        result = self.scenarios["section_breaker_open"]
        self.assertFalse(result["summary"]["bus_sections_same_equipotential_node"])
        self.assertEqual(result["summary"]["topological_region_count"], 2)
        self.assertEqual(result["summary"]["equipotential_node_count"], 4)

    def test_section_disconnector_open_separates_bus_sections(self):
        result = self.scenarios["section_disconnector_open"]
        self.assertTrue(result["switch_current_closed"]["QF-S"])
        self.assertFalse(result["summary"]["bus_sections_same_equipotential_node"])
        self.assertEqual(result["summary"]["topological_region_count"], 2)

    def test_l1_breaker_open_separates_external_region_not_bus_sections(self):
        result = self.scenarios["l1_breaker_open"]
        self.assertTrue(result["summary"]["bus_sections_same_equipotential_node"])
        self.assertEqual(result["summary"]["topological_region_count"], 2)

    def test_component_terminal_mapping_preserves_original_ports_and_roles(self):
        result = self.scenarios["all_switches_closed"]
        devices = {c["component_id"]: c for c in result["device_terminal_mapping"]}
        self.assertEqual(len(devices), 12)
        self.assertEqual(devices["T1"]["terminal_nodes"], ["n-10p5-I", "n-T1-hv"])
        self.assertEqual(devices["T1"]["terminal_roles"], ["lv", "hv"])
        self.assertEqual(len(devices["T1"]["calculation_terminal_nodes"]), 2)
        self.assertEqual(
            {e["component_id"] for e in result["non_switch_device_edges"]}, {"T1", "L1"}
        )

    def test_actual_unknown_states_rejected_despite_normal_label(self):
        self.assertTrue(
            next(c for c in self.draft["components"] if c["component_id"] == "QF-S")[
                "normal_closed"
            ]
        )
        with self.assertRaisesRegex(ConnectivityInputError, "explicit true/false"):
            compile_connectivity(self.draft)

    def test_missing_teaching_state_rejected(self):
        states = dict(self.switches)
        states.pop("QS-S1")
        with self.assertRaisesRegex(ConnectivityInputError, "exactly all switches"):
            self.compile_teaching(switches=states)

    def test_non_boolean_teaching_state_rejected(self):
        for invalid in [None, 0, 1, "closed", "false"]:
            with self.subTest(invalid=invalid):
                states = dict(self.switches, **{"QF-S": invalid})
                with self.assertRaisesRegex(
                    ConnectivityInputError, "explicit true/false"
                ):
                    self.compile_teaching(switches=states)

    def test_unknown_device_state_rejected(self):
        with self.assertRaisesRegex(ConnectivityInputError, "T1.in_service"):
            self.compile_teaching(devices=dict(self.devices, T1=None))

    def test_cross_voltage_switch_rejected(self):
        bad = copy.deepcopy(self.draft)
        switch = next(c for c in bad["components"] if c["component_id"] == "QS-S1")
        switch["terminal_nodes"][0] = "n-10p5-I"
        with self.assertRaisesRegex(ConnectivityInputError, "crosses voltage levels"):
            self.compile_teaching(draft=bad)

    def test_closed_switch_unknown_voltage_rejected(self):
        bad = copy.deepcopy(self.draft)
        next(n for n in bad["nodes"] if n["node_id"] == "n-S-QS1-QF")[
            "node_nominal_voltage_kv"
        ] = None
        with self.assertRaisesRegex(ConnectivityInputError, "voltage is unknown"):
            self.compile_teaching(draft=bad)

    def test_out_of_service_transformer_not_contracted_or_connecting_regions(self):
        result = self.compile_teaching(devices=dict(self.devices, T1=False))
        self.assertFalse(result["summary"]["transformer_hv_lv_same_equipotential_node"])
        self.assertEqual(result["summary"]["topological_region_count"], 2)

    def test_overrides_without_teaching_provenance_rejected(self):
        with self.assertRaisesRegex(
            ConnectivityInputError, "provenance must be explicit"
        ):
            self.compile_teaching(provenance={})

    def test_results_remain_connectivity_only_and_source_unmodified(self):
        for result in self.scenarios.values():
            self.assertEqual(result["analysis_kind"], "connectivity-only")
            self.assertEqual(result["state_origin"], "teaching-scenario")
            self.assertTrue(result["state_source"]["not_from_actual_drawing_state"])
            self.assertNotIn("voltage", result)
            self.assertNotIn("current", result)
            self.assertNotIn("energized", result)
        self.assertEqual(DEFAULT_SOURCE.read_bytes(), self.source_bytes)
        self.assertEqual(self.draft, json.loads(self.source_bytes))


if __name__ == "__main__":
    unittest.main()
