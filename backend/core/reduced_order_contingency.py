"""Deterministic N-1 line-outage study for the low-frequency network model.

Each in-service AC line is removed once.  Islanding cases are reported without
attempting a modal solve; connected cases rebuild the complete reduced-order
model.  This is a model-specific structural sensitivity study, not an AC power
flow security assessment or a statement of compliance.
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.core.reduced_order_model import build_reduced_order_model
from backend.domain.network_models import NetworkTopology


class ReducedOrderContingencyError(ValueError):
    """Raised when an N-1 request has no meaningful line-outage cases."""


@dataclass(frozen=True)
class LineOutageCase:
    line_id: str
    line_name: str
    outcome: str
    disconnected_bus_ids: tuple[str, ...]
    stability: str | None = None
    dominant_real_per_s: float | None = None
    dominant_real_hz: float | None = None
    oscillation_frequency_hz: float | None = None
    spectral_abscissa_shift_per_s: float | None = None
    stability_changed: bool | None = None

    def as_dict(self) -> dict:
        return {
            "line_id": self.line_id,
            "line_name": self.line_name,
            "outcome": self.outcome,
            "disconnected_bus_ids": list(self.disconnected_bus_ids),
            "stability": self.stability,
            "dominant_real_per_s": self.dominant_real_per_s,
            "dominant_real_hz": self.dominant_real_hz,
            "oscillation_frequency_hz": self.oscillation_frequency_hz,
            "spectral_abscissa_shift_per_s": self.spectral_abscissa_shift_per_s,
            "stability_changed": self.stability_changed,
        }


@dataclass(frozen=True)
class LineOutageStudy:
    topology_id: str
    base_stability: str
    base_dominant_real_per_s: float
    cases: tuple[LineOutageCase, ...]

    @property
    def counts(self) -> dict[str, int]:
        analyzed = tuple(case for case in self.cases if case.outcome == "analyzed")
        return {
            "total": len(self.cases),
            "analyzed": len(analyzed),
            "islanding": sum(case.outcome == "islanding" for case in self.cases),
            "stable": sum(case.stability == "stable" for case in analyzed),
            "marginal": sum(case.stability == "marginal" for case in analyzed),
            "unstable": sum(case.stability == "unstable" for case in analyzed),
            "stability_changed": sum(case.stability_changed is True for case in analyzed),
        }

    def as_dict(self) -> dict:
        return {
            "topology_id": self.topology_id,
            "base_stability": self.base_stability,
            "base_dominant_real_per_s": self.base_dominant_real_per_s,
            "counts": self.counts,
            "cases": [case.as_dict() for case in self.cases],
        }


def _disconnected_buses(topology: NetworkTopology, removed_line_id: str) -> tuple[str, ...]:
    adjacency = {bus.id: set() for bus in topology.buses}
    for line in topology.lines:
        if not line.in_service or line.id == removed_line_id:
            continue
        adjacency[line.from_bus_id].add(line.to_bus_id)
        adjacency[line.to_bus_id].add(line.from_bus_id)

    visited: set[str] = set()
    pending = [topology.reference_bus_id]
    while pending:
        bus_id = pending.pop()
        if bus_id in visited:
            continue
        visited.add(bus_id)
        pending.extend(adjacency[bus_id] - visited)
    return tuple(sorted(set(adjacency) - visited))


def evaluate_line_outages(topology: NetworkTopology) -> LineOutageStudy:
    """Remove every in-service line once and rebuild connected cases."""

    if not isinstance(topology, NetworkTopology):
        raise TypeError("topology 必须是经过校验的 NetworkTopology 实例。")
    baseline = NetworkTopology.model_validate(topology.model_dump(mode="python"))
    active_lines = tuple(line for line in baseline.lines if line.in_service)
    if not active_lines:
        raise ReducedOrderContingencyError("N−1 支路校核至少需要一条投运交流线路。")

    base_model = build_reduced_order_model(baseline)
    base_real = float(base_model.dominant_mode.eigenvalue_per_s.real)
    cases: list[LineOutageCase] = []
    for line in active_lines:
        disconnected = _disconnected_buses(baseline, line.id)
        if disconnected:
            cases.append(
                LineOutageCase(
                    line_id=line.id,
                    line_name=line.name,
                    outcome="islanding",
                    disconnected_bus_ids=disconnected,
                )
            )
            continue

        case_data = baseline.model_dump(mode="python")
        case_data["id"] = f"{baseline.id}-without-{line.id}"[:64]
        case_data["lines"] = [item for item in case_data["lines"] if item["id"] != line.id]
        outage_topology = NetworkTopology.model_validate(case_data)
        outage_model = build_reduced_order_model(outage_topology)
        dominant = outage_model.dominant_mode
        cases.append(
            LineOutageCase(
                line_id=line.id,
                line_name=line.name,
                outcome="analyzed",
                disconnected_bus_ids=(),
                stability=outage_model.stability.value,
                dominant_real_per_s=float(dominant.eigenvalue_per_s.real),
                dominant_real_hz=float(dominant.pole_hz.real),
                oscillation_frequency_hz=float(dominant.oscillation_frequency_hz),
                spectral_abscissa_shift_per_s=float(
                    dominant.eigenvalue_per_s.real - base_real
                ),
                stability_changed=(outage_model.stability != base_model.stability),
            )
        )

    return LineOutageStudy(
        topology_id=baseline.id,
        base_stability=base_model.stability.value,
        base_dominant_real_per_s=base_real,
        cases=tuple(cases),
    )
