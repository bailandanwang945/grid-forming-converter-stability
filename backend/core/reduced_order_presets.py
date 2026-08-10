"""Traceable analytic presets for the reduced-order VSM model.

These cases are team-defined verification fixtures.  They are deliberately
separate from the Cifelli--Anta Fig. 8 author fixture and must not be cited as a
reproduction of the paper's complete converter model or theorem conditions.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import pi, sqrt

from backend.domain.network_models import NetworkTopology


MODEL_FAMILY_ID = "team-reduced-order-smib-v1"
INERTIA_S = 2.0
MEASUREMENT_TIME_CONSTANT_S = 0.1
LINE_RESISTANCE_PU = 0.02
LINE_REACTANCE_PU = 0.2
SYNCHRONOUS_STIFFNESS_PU_PER_RAD = 1.0 / LINE_REACTANCE_PU
BASE_FREQUENCY_HZ = 50.0
BASE_ANGULAR_FREQUENCY_PER_S = 2.0 * pi * BASE_FREQUENCY_HZ


def analytic_critical_damping() -> float:
    """Return the scalar Routh--Hurwitz boundary for the preset family."""

    inertia = INERTIA_S
    measurement_time = MEASUREMENT_TIME_CONSTANT_S
    stiffness = SYNCHRONOUS_STIFFNESS_PU_PER_RAD
    return (
        -inertia
        + sqrt(
            inertia**2
            + 4.0
            * inertia
            * measurement_time**2
            * BASE_ANGULAR_FREQUENCY_PER_S
            * stiffness
        )
    ) / (2.0 * measurement_time)


@dataclass(frozen=True)
class ReducedOrderPresetDefinition:
    """Immutable metadata from which a fresh validated topology is built."""

    id: str
    name: str
    description: str
    damping: float
    expected_stability: str

    def build_topology(self) -> NetworkTopology:
        return NetworkTopology.model_validate(
            {
                "id": self.id,
                "name": self.name,
                "base_values": {
                    "apparent_power_va": 1.0e6,
                    "voltage_v": 690.0,
                    "frequency_hz": BASE_FREQUENCY_HZ,
                },
                "frame_convention_id": "global-synchronous-angle-v1",
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
                        "name": "并网线路",
                        "from_bus_id": "bus-gfm",
                        "to_bus_id": "bus-grid",
                        "resistance_pu": LINE_RESISTANCE_PU,
                        "reactance_pu": LINE_REACTANCE_PU,
                    }
                ],
                "grid_forming_converters": [
                    {
                        "id": "gfm-1",
                        "name": "VSM 构网型变流器",
                        "bus_id": "bus-gfm",
                        "rated_apparent_power_va": 1.0e6,
                        "control_mode": "virtual_synchronous_machine",
                        "active_power_setpoint_pu": 0.0,
                        "reactive_power_setpoint_pu": 0.0,
                        "voltage_setpoint_pu": 1.0,
                        "virtual_inertia_s": INERTIA_S,
                        "damping_coefficient_pu": self.damping,
                        "active_power_measurement_time_constant_s": (
                            MEASUREMENT_TIME_CONSTANT_S
                        ),
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

    def provenance(self) -> dict:
        return {
            "source_kind": "team-defined-analytic-verification-preset",
            "model_family_id": MODEL_FAMILY_ID,
            "paper_fixture": False,
            "characteristic_polynomial": (
                "M*T_p*s^3 + (M + D*T_p)*s^2 + D*s + omega_b*K = 0"
            ),
            "critical_boundary": "D*(M + D*T_p) = M*T_p*omega_b*K",
            "critical_damping": analytic_critical_damping(),
            "parameters": {
                "M_s": INERTIA_S,
                "D_pu": self.damping,
                "T_p_s": MEASUREMENT_TIME_CONSTANT_S,
                "line_R_pu_ignored_by_model": LINE_RESISTANCE_PU,
                "line_X_pu": LINE_REACTANCE_PU,
                "K_pu_per_rad": SYNCHRONOUS_STIFFNESS_PU_PER_RAD,
                "omega_b_per_s": BASE_ANGULAR_FREQUENCY_PER_S,
            },
        }


_PRESETS = (
    ReducedOrderPresetDefinition(
        id="reduced-smib-stable",
        name="低频降阶单机系统：稳定",
        description="阻尼高于解析临界值的团队自建校核算例。",
        damping=60.0,
        expected_stability="stable",
    ),
    ReducedOrderPresetDefinition(
        id="reduced-smib-critical",
        name="低频降阶单机系统：临界",
        description="阻尼取 Routh--Hurwitz 解析边界的团队自建校核算例。",
        damping=analytic_critical_damping(),
        expected_stability="marginal",
    ),
    ReducedOrderPresetDefinition(
        id="reduced-smib-unstable",
        name="低频降阶单机系统：失稳",
        description="阻尼低于解析临界值的团队自建校核算例。",
        damping=0.05,
        expected_stability="unstable",
    ),
)


def available_reduced_order_presets() -> tuple[ReducedOrderPresetDefinition, ...]:
    return _PRESETS


def get_reduced_order_preset(preset_id: str) -> ReducedOrderPresetDefinition:
    for preset in _PRESETS:
        if preset.id == preset_id:
            return preset
    raise ValueError(f"未知的低频降阶模型预设：{preset_id!r}。")
