"""Traceable verification preset for the transparent average-value dq model."""

from __future__ import annotations

from backend.domain.average_dq_models import (
    AverageDQGFMParameters,
    default_average_dq_parameters,
)
from backend.domain.network_models import NetworkTopology


PRESET_ID = "average-dq-smib-verification"


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
