"""Traceable verification preset for the transparent average-value dq model."""

from __future__ import annotations

from backend.domain.average_dq_models import (
    AverageDQGFMParameters,
    default_average_dq_parameters,
)
from backend.domain.network_models import NetworkTopology


PRESET_ID = "average-dq-smib-verification"
ABLATION_PRESET_ID = "average-dq-hierarchy-disagreement-ablation-v1"


def build_average_dq_verification_case() -> tuple[
    NetworkTopology, AverageDQGFMParameters
]:
    """Return a fresh loaded SMIB case used for software verification.

    This is a team-defined deterministic case.  It is not the Cifelli--Anta
    Fig. 8 model and is not fitted to a physical converter data sheet.
    """

    parameters = default_average_dq_parameters(converter_id="gfm-1")
    topology = NetworkTopology.model_validate(
        {
            "id": PRESET_ID,
            "name": "平均值 dq 单机无穷大母线校核算例",
            "base_values": {
                "apparent_power_va": 1.0e6,
                "voltage_v": 690.0,
                "frequency_hz": 50.0,
            },
            "frame_convention_id": parameters.frame_convention_id,
            "reference_bus_id": "bus-grid",
            "buses": [
                {
                    "id": "bus-gfm",
                    "name": "构网型变流器节点",
                    "nominal_voltage_v": 690.0,
                },
                {
                    "id": "bus-grid",
                    "name": "无限大母线节点",
                    "nominal_voltage_v": 690.0,
                },
            ],
            "lines": [
                {
                    "id": "line-grid",
                    "name": "外部串联 RL 线路",
                    "from_bus_id": "bus-gfm",
                    "to_bus_id": "bus-grid",
                    "resistance_pu": 0.02,
                    "reactance_pu": 0.30,
                    "shunt_susceptance_pu": 0.0,
                }
            ],
            "grid_forming_converters": [
                {
                    "id": "gfm-1",
                    "name": "平均值 dq VSM",
                    "bus_id": "bus-gfm",
                    "rated_apparent_power_va": 1.0e6,
                    "control_mode": "virtual_synchronous_machine",
                    "active_power_setpoint_pu": 0.5,
                    "reactive_power_setpoint_pu": 0.1,
                    "voltage_setpoint_pu": 1.0,
                    "virtual_inertia_s": 2.0,
                    "damping_coefficient_pu": 60.0,
                    "active_power_measurement_time_constant_s": 0.1,
                    "parameter_set_id": parameters.id,
                }
            ],
            "infinite_buses": [
                {
                    "id": "grid-1",
                    "name": "理想无限大母线",
                    "bus_id": "bus-grid",
                    "voltage_magnitude_pu": 1.0,
                    "voltage_angle_deg": 0.0,
                }
            ],
            "loads": [],
        }
    )
    return topology, parameters


def build_average_dq_ablation_anchor_case() -> tuple[
    NetworkTopology, AverageDQGFMParameters
]:
    """Return a fresh copy of the fixed model-hierarchy ablation anchor.

    The anchor is derived from the ordinary average-value verification case,
    then fixes VSM damping to ``D=60`` and external-line reactance to
    ``X=0.1 pu``.  It belongs to the team's fixed 19-point ablation study; it
    is neither the paper's Fig. 8 case nor a physical-hardware fit, and its
    state definition is fixed rather than supplied by callers.
    """

    verification_topology, verification_parameters = (
        build_average_dq_verification_case()
    )
    topology = verification_topology.model_copy(deep=True)
    parameters = verification_parameters.model_copy(deep=True)

    matching_converters = [
        converter
        for converter in topology.grid_forming_converters
        if converter.id == parameters.converter_id
    ]
    matching_lines = [line for line in topology.lines if line.id == "line-grid"]
    if len(matching_converters) != 1 or len(matching_lines) != 1:
        raise RuntimeError(
            "普通平均值校核算例不再包含唯一的 gfm-1 与 line-grid，"
            "无法构造固定消融锚点。"
        )

    topology.id = ABLATION_PRESET_ID
    topology.name = "平均值 dq 模型层级分歧固定消融锚点"
    matching_converters[0].damping_coefficient_pu = 60.0
    matching_lines[0].reactance_pu = 0.1
    return topology, parameters


def average_dq_ablation_anchor_metadata() -> dict[str, object]:
    """Describe the immutable research boundary of the ablation anchor."""

    return {
        "id": ABLATION_PRESET_ID,
        "name": "平均值 dq 模型层级分歧固定消融锚点",
        "study_point_count": 19,
        "paper_fig8_fixture": False,
        "physical_hardware_fit": False,
        "accepts_arbitrary_state_definition": False,
        "source_kind": "team-defined-fixed-average-dq-ablation-anchor",
        "interpretation_boundary": (
            "团队固定 19 点模型层级消融；非论文 Fig. 8，非硬件拟合，"
            "不接受任意状态定义。"
        ),
    }


def average_dq_preset_metadata() -> dict:
    topology, parameters = build_average_dq_verification_case()
    return {
        "id": PRESET_ID,
        "name": "平均值 dq 单机校核算例",
        "description": (
            "团队定义的16状态平均值模型校核算例，保留 LCL、电压电流内环、"
            "VSM、Q–V 下垂、调制延迟和外部 RL 线路。"
        ),
        "expected_stability": "stable",
        "topology": topology.model_dump(mode="json"),
        "parameters": parameters.model_dump(mode="json"),
        "provenance": {
            "source_kind": "team-defined-average-dq-verification-preset",
            "paper_fixture": False,
            "physical_hardware_fit": False,
            "model_specification": "docs/specs/models/average-dq-gfm-v1-proposal.md",
        },
    }
