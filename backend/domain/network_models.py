"""Validated data contracts for editable AC-network topologies.

The contracts in this module describe topology and nameplate/operating-point
parameters only.  They do not claim that a corresponding small-signal model or
stability criterion has already been assembled.  Per-unit quantities use the
explicit :class:`BaseValues` supplied with each case.

Sign convention
---------------
Grid-forming-converter active and reactive power setpoints are positive when
injected into the network.  Static-load powers are positive when consumed from
the network.  The two meanings are kept in separate models intentionally.
"""

from __future__ import annotations

from collections import Counter
from enum import Enum
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    model_validator,
)


Identifier = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=64,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]*$",
    ),
]


class DomainModel(BaseModel):
    """Shared strictness settings for external topology input."""

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        allow_inf_nan=False,
        validate_assignment=True,
    )


class BaseValues(DomainModel):
    """Base quantities used to interpret every per-unit parameter in a case."""

    apparent_power_va: float = Field(gt=0.0, le=1.0e12)
    voltage_v: float = Field(gt=0.0, le=1.0e9)
    frequency_hz: float = Field(ge=1.0, le=1000.0)


class Bus(DomainModel):
    """Electrical node at one nominal voltage level."""

    kind: Literal["bus"] = "bus"
    id: Identifier
    name: str = Field(min_length=1, max_length=120)
    nominal_voltage_v: float = Field(gt=0.0, le=1.0e9)


class ACLine(DomainModel):
    """Positive-sequence AC line represented on the case base values."""

    kind: Literal["ac_line"] = "ac_line"
    id: Identifier
    name: str = Field(min_length=1, max_length=120)
    from_bus_id: Identifier
    to_bus_id: Identifier
    resistance_pu: float = Field(ge=0.0, le=100.0)
    reactance_pu: float = Field(gt=0.0, le=100.0)
    shunt_susceptance_pu: float = Field(default=0.0, ge=-100.0, le=100.0)
    thermal_limit_pu: float | None = Field(default=None, gt=0.0, le=1000.0)

    @model_validator(mode="after")
    def reject_self_loop(self) -> "ACLine":
        if self.from_bus_id == self.to_bus_id:
            raise ValueError(
                f"交流线路 {self.id!r} 的首、末端节点不能相同；"
                "若需表示并联支路，应使用不同的线路 ID。"
            )
        return self


class GFMControlMode(str, Enum):
    """Controller families covered by the topology input contract."""

    VIRTUAL_SYNCHRONOUS_MACHINE = "virtual_synchronous_machine"
    DROOP = "droop"
    USER_DEFINED = "user_defined"


class GridFormingConverter(DomainModel):
    """Grid-forming converter and controller parameter reference."""

    kind: Literal["grid_forming_converter"] = "grid_forming_converter"
    id: Identifier
    name: str = Field(min_length=1, max_length=120)
    bus_id: Identifier
    rated_apparent_power_va: float = Field(gt=0.0, le=1.0e12)
    control_mode: GFMControlMode
    active_power_setpoint_pu: float = Field(default=0.0, ge=-2.0, le=2.0)
    reactive_power_setpoint_pu: float = Field(default=0.0, ge=-2.0, le=2.0)
    voltage_setpoint_pu: float = Field(default=1.0, ge=0.5, le=1.5)
    virtual_inertia_s: float | None = Field(default=None, gt=0.0, le=1000.0)
    damping_coefficient_pu: float | None = Field(
        default=None, gt=0.0, le=1.0e4
    )
    active_power_measurement_time_constant_s: float | None = Field(
        default=None, gt=0.0, le=1000.0
    )
    active_power_frequency_droop_pu: float | None = Field(
        default=None, gt=0.0, le=1.0
    )
    reactive_power_voltage_droop_pu: float | None = Field(
        default=None, gt=0.0, le=1.0
    )
    parameter_set_id: Identifier | None = None

    @model_validator(mode="after")
    def require_controller_parameters(self) -> "GridFormingConverter":
        if self.control_mode is GFMControlMode.VIRTUAL_SYNCHRONOUS_MACHINE:
            missing = [
                field_name
                for field_name, value in (
                    ("virtual_inertia_s", self.virtual_inertia_s),
                    ("damping_coefficient_pu", self.damping_coefficient_pu),
                    (
                        "active_power_measurement_time_constant_s",
                        self.active_power_measurement_time_constant_s,
                    ),
                )
                if value is None
            ]
            if missing:
                raise ValueError(
                    "虚拟同步机控制必须给出 " + "、".join(missing) + "。"
                )
        elif self.control_mode is GFMControlMode.DROOP:
            missing = [
                field_name
                for field_name, value in (
                    (
                        "active_power_frequency_droop_pu",
                        self.active_power_frequency_droop_pu,
                    ),
                    (
                        "reactive_power_voltage_droop_pu",
                        self.reactive_power_voltage_droop_pu,
                    ),
                )
                if value is None
            ]
            if missing:
                raise ValueError("下垂控制必须给出 " + "、".join(missing) + "。")
        elif self.parameter_set_id is None:
            raise ValueError("自定义控制必须给出可追溯的 parameter_set_id。")
        return self


class InfiniteBus(DomainModel):
    """Ideal voltage source used as an infinite-bus boundary condition."""

    kind: Literal["infinite_bus"] = "infinite_bus"
    id: Identifier
    name: str = Field(min_length=1, max_length=120)
    bus_id: Identifier
    voltage_magnitude_pu: float = Field(default=1.0, ge=0.5, le=1.5)
    voltage_angle_deg: float = Field(default=0.0, ge=-180.0, le=180.0)


class LoadModel(str, Enum):
    """Static load behaviours currently representable by the contract."""

    CONSTANT_POWER = "constant_power"
    CONSTANT_IMPEDANCE = "constant_impedance"


class StaticLoad(DomainModel):
    """Balanced static load; positive powers denote network consumption."""

    kind: Literal["static_load"] = "static_load"
    id: Identifier
    name: str = Field(min_length=1, max_length=120)
    bus_id: Identifier
    load_model: LoadModel = LoadModel.CONSTANT_POWER
    active_power_pu: float = Field(ge=0.0, le=100.0)
    reactive_power_pu: float = Field(default=0.0, ge=-100.0, le=100.0)


class NetworkTopology(DomainModel):
    """A connected network case with one explicit angular reference node."""

    schema_version: Literal["1.0"] = "1.0"
    id: Identifier
    name: str = Field(min_length=1, max_length=120)
    base_values: BaseValues
    frame_convention_id: Identifier
    reference_bus_id: Identifier
    buses: list[Bus] = Field(min_length=1)
    lines: list[ACLine] = Field(default_factory=list)
    grid_forming_converters: list[GridFormingConverter] = Field(
        default_factory=list
    )
    infinite_buses: list[InfiniteBus] = Field(default_factory=list)
    loads: list[StaticLoad] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_network(self) -> "NetworkTopology":
        entities: list[tuple[str, str]] = [
            *((bus.id, "节点") for bus in self.buses),
            *((line.id, "交流线路") for line in self.lines),
            *((gfm.id, "构网型变流器") for gfm in self.grid_forming_converters),
            *((source.id, "无限大母线") for source in self.infinite_buses),
            *((load.id, "静态负荷") for load in self.loads),
        ]
        counts = Counter(entity_id for entity_id, _ in entities)
        duplicate_ids = sorted(entity_id for entity_id, count in counts.items() if count > 1)
        if duplicate_ids:
            raise ValueError(
                "网络实体 ID 必须全局唯一；重复 ID：" + "、".join(duplicate_ids) + "。"
            )

        buses_by_id = {bus.id: bus for bus in self.buses}
        if self.reference_bus_id not in buses_by_id:
            raise ValueError(
                f"参考节点 {self.reference_bus_id!r} 不存在于 buses 中。"
            )

        for line in self.lines:
            for terminal_name, bus_id in (
                ("首端", line.from_bus_id),
                ("末端", line.to_bus_id),
            ):
                if bus_id not in buses_by_id:
                    raise ValueError(
                        f"交流线路 {line.id!r} 的{terminal_name}节点 {bus_id!r} 不存在。"
                    )
            from_voltage = buses_by_id[line.from_bus_id].nominal_voltage_v
            to_voltage = buses_by_id[line.to_bus_id].nominal_voltage_v
            relative_difference = abs(from_voltage - to_voltage) / max(
                from_voltage, to_voltage
            )
            if relative_difference > 1.0e-9:
                raise ValueError(
                    f"交流线路 {line.id!r} 连接了不同标称电压等级的节点；"
                    "当前契约不以线路替代变压器模型。"
                )

        attached_elements = [
            *((gfm.id, "构网型变流器", gfm.bus_id) for gfm in self.grid_forming_converters),
            *((source.id, "无限大母线", source.bus_id) for source in self.infinite_buses),
            *((load.id, "静态负荷", load.bus_id) for load in self.loads),
        ]
        for element_id, element_type, bus_id in attached_elements:
            if bus_id not in buses_by_id:
                raise ValueError(
                    f"{element_type} {element_id!r} 所连接的节点 {bus_id!r} 不存在。"
                )

        if not self.grid_forming_converters and not self.infinite_buses:
            raise ValueError("网络至少需要一个构网型变流器或无限大母线作为成网电压源。")

        infinite_bus_nodes = [source.bus_id for source in self.infinite_buses]
        repeated_infinite_bus_nodes = sorted(
            bus_id
            for bus_id, count in Counter(infinite_bus_nodes).items()
            if count > 1
        )
        if repeated_infinite_bus_nodes:
            raise ValueError(
                "同一节点不能并联多个理想无限大母线；涉及节点："
                + "、".join(repeated_infinite_bus_nodes)
                + "。"
            )

        adjacency = {bus_id: set() for bus_id in buses_by_id}
        for line in self.lines:
            adjacency[line.from_bus_id].add(line.to_bus_id)
            adjacency[line.to_bus_id].add(line.from_bus_id)

        visited: set[str] = set()
        pending = [self.reference_bus_id]
        while pending:
            bus_id = pending.pop()
            if bus_id in visited:
                continue
            visited.add(bus_id)
            pending.extend(adjacency[bus_id] - visited)

        disconnected = sorted(set(buses_by_id) - visited)
        if disconnected:
            raise ValueError(
                f"网络拓扑不连通；相对于参考节点 {self.reference_bus_id!r} "
                "不可达的节点为："
                + "、".join(disconnected)
                + "。"
            )

        return self
