from __future__ import annotations

import inspect
import unittest

from backend.core.average_dq_presets import (
    ABLATION_PRESET_ID,
    average_dq_ablation_anchor_metadata,
    build_average_dq_ablation_anchor_case,
    build_average_dq_verification_case,
)


class AverageDQAblationPresetTest(unittest.TestCase):
    def test_returns_independent_deep_copies(self) -> None:
        first_topology, first_parameters = build_average_dq_ablation_anchor_case()
        second_topology, second_parameters = build_average_dq_ablation_anchor_case()

        self.assertIsNot(first_topology, second_topology)
        self.assertIsNot(first_parameters, second_parameters)
        self.assertIsNot(first_topology.lines[0], second_topology.lines[0])
        self.assertIsNot(
            first_topology.grid_forming_converters[0],
            second_topology.grid_forming_converters[0],
        )

        first_topology.lines[0].reactance_pu = 0.2
        first_topology.grid_forming_converters[0].damping_coefficient_pu = 75.0
        first_parameters.current_proportional_gain_pu = 0.4

        self.assertEqual(second_topology.lines[0].reactance_pu, 0.1)
        self.assertEqual(
            second_topology.grid_forming_converters[0].damping_coefficient_pu,
            60.0,
        )
        self.assertEqual(second_parameters.current_proportional_gain_pu, 0.3)

        verification_topology, verification_parameters = (
            build_average_dq_verification_case()
        )
        self.assertEqual(verification_topology.lines[0].reactance_pu, 0.3)
        self.assertEqual(verification_parameters.current_proportional_gain_pu, 0.3)

    def test_anchor_changes_only_the_declared_case_fields(self) -> None:
        verification_topology, verification_parameters = (
            build_average_dq_verification_case()
        )
        anchor_topology, anchor_parameters = build_average_dq_ablation_anchor_case()

        expected_topology = verification_topology.model_copy(deep=True)
        expected_topology.id = ABLATION_PRESET_ID
        expected_topology.name = "平均值 dq 模型层级分歧固定消融锚点"
        expected_topology.grid_forming_converters[0].damping_coefficient_pu = 60.0
        expected_topology.lines[0].reactance_pu = 0.1

        self.assertEqual(anchor_topology, expected_topology)
        self.assertEqual(anchor_parameters, verification_parameters)
        self.assertEqual(anchor_topology.id, ABLATION_PRESET_ID)
        self.assertEqual(anchor_topology.lines[0].id, "line-grid")
        self.assertEqual(anchor_topology.lines[0].reactance_pu, 0.1)
        self.assertEqual(
            anchor_topology.grid_forming_converters[0].damping_coefficient_pu,
            60.0,
        )

    def test_metadata_and_signature_fix_the_research_boundary(self) -> None:
        metadata = average_dq_ablation_anchor_metadata()

        self.assertEqual(metadata["id"], ABLATION_PRESET_ID)
        self.assertEqual(metadata["study_point_count"], 19)
        self.assertFalse(metadata["paper_fig8_fixture"])
        self.assertFalse(metadata["physical_hardware_fit"])
        self.assertFalse(metadata["accepts_arbitrary_state_definition"])
        self.assertIn("团队固定 19 点", metadata["interpretation_boundary"])
        self.assertIn("非论文 Fig. 8", metadata["interpretation_boundary"])
        self.assertIn("非硬件拟合", metadata["interpretation_boundary"])
        self.assertIn("不接受任意状态定义", metadata["interpretation_boundary"])
        self.assertEqual(
            inspect.signature(build_average_dq_ablation_anchor_case).parameters,
            {},
        )


if __name__ == "__main__":
    unittest.main()
