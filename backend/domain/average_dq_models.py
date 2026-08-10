"""Strict parameter contracts for the transparent average-value dq model."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from backend.domain.network_models import DomainModel, Identifier


class AverageDQGFMParameters(DomainModel):
    """Controller and LCL parameters on the topology's common per-unit base.

    The VSM inertia, damping, active-power setpoint, reactive-power setpoint,
    voltage setpoint, and active-power measurement time constant remain owned
    by :class:`GridFormingConverter`.  This object contains only the additional
    quantities required by the 16-state average-value model.
    """

    schema_version: Literal["1.0"] = "1.0"
    id: Identifier
    converter_id: Identifier
    frame_convention_id: Literal["power-invariant-park-q-lag-v1"] = (
        "power-invariant-park-q-lag-v1"
    )

    converter_side_resistance_pu: float = Field(ge=0.0, le=10.0)
    converter_side_reactance_pu: float = Field(gt=0.0, le=10.0)
    filter_capacitor_susceptance_pu: float = Field(gt=0.0, le=10.0)
    grid_side_resistance_pu: float = Field(ge=0.0, le=10.0)
    grid_side_reactance_pu: float = Field(gt=0.0, le=10.0)
    modulation_time_constant_s: float = Field(gt=0.0, le=1.0)

    reactive_power_measurement_time_constant_s: float = Field(gt=0.0, le=10.0)
    reactive_power_voltage_droop_pu: float = Field(ge=0.0, le=10.0)
    voltage_proportional_gain_pu: float = Field(ge=0.0, le=1.0e4)
    voltage_integral_gain_per_s: float = Field(gt=0.0, le=1.0e6)
    current_proportional_gain_pu: float = Field(ge=0.0, le=1.0e4)
    current_integral_gain_per_s: float = Field(gt=0.0, le=1.0e6)

    virtual_resistance_pu: float = Field(default=0.0, ge=0.0, le=10.0)
    virtual_reactance_pu: float = Field(default=0.0, ge=0.0, le=10.0)
    diagnostic_current_limit_pu: float = Field(default=2.0, gt=0.0, le=100.0)
    diagnostic_internal_voltage_limit_pu: float = Field(
        default=1.5, gt=0.0, le=100.0
    )

    @model_validator(mode="after")
    def require_meaningful_voltage_controller(self) -> "AverageDQGFMParameters":
        if (
            self.voltage_proportional_gain_pu == 0.0
            and self.voltage_integral_gain_per_s <= 0.0
        ):
            raise ValueError("电压控制器至少需要一个非零增益。")
        return self


def default_average_dq_parameters(
    *, converter_id: str = "gfm-1"
) -> AverageDQGFMParameters:
    """Return a traceable starter set for numerical verification.

    The values are engineering test parameters, not a claim that they reproduce
    a particular commercial converter or the Cifelli--Anta Fig. 8 model.
    """

    return AverageDQGFMParameters(
        id="average-dq-default-v1",
        converter_id=converter_id,
        converter_side_resistance_pu=0.01,
        converter_side_reactance_pu=0.15,
        filter_capacitor_susceptance_pu=0.05,
        grid_side_resistance_pu=0.01,
        grid_side_reactance_pu=0.10,
        modulation_time_constant_s=1.0e-3,
        reactive_power_measurement_time_constant_s=0.02,
        reactive_power_voltage_droop_pu=0.05,
        voltage_proportional_gain_pu=0.3,
        voltage_integral_gain_per_s=5.0,
        current_proportional_gain_pu=0.3,
        current_integral_gain_per_s=5.0,
        virtual_resistance_pu=0.0,
        virtual_reactance_pu=0.0,
        diagnostic_current_limit_pu=2.0,
        diagnostic_internal_voltage_limit_pu=1.5,
    )
