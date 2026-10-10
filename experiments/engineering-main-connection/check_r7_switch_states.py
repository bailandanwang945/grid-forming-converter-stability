"""Check R7 switch connectivity only; never solve power flow or fault currents."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SOURCE = ROOT / "examples/engineering-main-connection/r7-subnetwork-draft.json"
DEFAULT_OUTPUT = (
    ROOT / "results/engineering-main-connection/r7-switch-connectivity-2026-10-06.json"
)
SWITCH_KINDS = {"disconnector", "circuit_breaker"}
DEVICE_KINDS = {
    "synchronous_generator",
    "two_winding_transformer",
    "system_tie_line",
}


class ConnectivityInputError(ValueError):
    """Input does not define a safe, unambiguous connectivity scenario."""


def _required_bool(value: object, label: str) -> bool:
    if type(value) is not bool:
        raise ConnectivityInputError(
            f"{label}: explicit true/false required, got {value!r}"
        )
    return value


def compile_connectivity(
    draft: dict,
    *,
    switch_overrides: dict[str, bool] | None = None,
    device_overrides: dict[str, bool] | None = None,
    state_source: dict | None = None,
) -> dict:
    """Contract ideal closed switches without contracting transformer/line bodies.

    Without overrides, actual states must exist in the source. Normal operating
    labels and drawn switch symbols do not supply actual states. Teaching
    overrides must define every switch and every device explicitly.
    """
    if draft.get("schema") != "EngineeringMainConnectionDraft/0.1":
        raise ConnectivityInputError("Unsupported engineering draft schema")
    if (switch_overrides is None) != (device_overrides is None):
        raise ConnectivityInputError(
            "Switch and device overrides must be supplied together"
        )

    nodes = {n["node_id"]: n for n in draft["nodes"]}
    if len(nodes) != len(draft["nodes"]):
        raise ConnectivityInputError("Duplicate node identifiers")
    components = {c["component_id"]: c for c in draft["components"]}
    if len(components) != len(draft["components"]):
        raise ConnectivityInputError("Duplicate component identifiers")
    switches = {k: c for k, c in components.items() if c["kind"] in SWITCH_KINDS}
    devices = {k: c for k, c in components.items() if c["kind"] in DEVICE_KINDS}
    if len(switches) + len(devices) != len(components):
        raise ConnectivityInputError(
            "Unsupported component kind in this bounded checker"
        )

    for node in nodes.values():
        voltage = node.get("node_nominal_voltage_kv")
        if voltage is not None and (
            isinstance(voltage, bool)
            or not isinstance(voltage, (int, float))
            or not math.isfinite(voltage)
            or voltage <= 0
        ):
            raise ConnectivityInputError("Invalid node nominal voltage")
    for component in components.values():
        terminals = component["terminal_nodes"]
        expected = 1 if component["kind"] == "synchronous_generator" else 2
        if len(terminals) != expected or len(set(terminals)) != len(terminals):
            raise ConnectivityInputError(
                f"Invalid terminals: {component['component_id']}"
            )
        if any(n not in nodes for n in terminals):
            raise ConnectivityInputError(
                f"Unresolved terminal: {component['component_id']}"
            )

    teaching = switch_overrides is not None
    if teaching:
        if set(switch_overrides) != set(switches):
            raise ConnectivityInputError(
                "Teaching overrides must cover exactly all switches"
            )
        if set(device_overrides) != set(devices):
            raise ConnectivityInputError(
                "Teaching overrides must cover exactly all devices"
            )
        if (
            not state_source
            or state_source.get("origin") != "explicit-teaching-assumption"
        ):
            raise ConnectivityInputError("Teaching state provenance must be explicit")
    elif state_source is not None:
        raise ConnectivityInputError(
            "Actual-state provenance is read from the source draft"
        )

    switch_states = {
        k: _required_bool(
            switch_overrides[k] if teaching else c.get("current_closed"),
            f"{k}.current_closed",
        )
        for k, c in switches.items()
    }
    device_states = {
        k: _required_bool(
            device_overrides[k]
            if teaching
            else c.get("parameters", {}).get("in_service"),
            f"{k}.in_service",
        )
        for k, c in devices.items()
    }

    parent = {n: n for n in nodes}

    def find(node_id: str) -> str:
        while parent[node_id] != node_id:
            parent[node_id] = parent[parent[node_id]]
            node_id = parent[node_id]
        return node_id

    for component_id, component in switches.items():
        a, b = component["terminal_nodes"]
        va = nodes[a].get("node_nominal_voltage_kv")
        vb = nodes[b].get("node_nominal_voltage_kv")
        if va is not None and vb is not None and va != vb:
            raise ConnectivityInputError(
                f"Switch crosses voltage levels: {component_id}"
            )
        if switch_states[component_id]:
            if va is None or vb is None:
                raise ConnectivityInputError(
                    f"Closed switch voltage is unknown: {component_id}"
                )
            ra, rb = find(a), find(b)
            parent[max(ra, rb)] = min(ra, rb)

    group_members: dict[str, list[str]] = {}
    for node_id in sorted(nodes):
        group_members.setdefault(find(node_id), []).append(node_id)
    node_map = {}
    equipotential_groups = []
    for index, (_, members) in enumerate(sorted(group_members.items()), start=1):
        calculation_id = f"eq-{index:03d}"
        node_map.update({n: calculation_id for n in members})
        equipotential_groups.append(
            {"calculation_node_id": calculation_id, "engineering_node_ids": members}
        )

    adjacency = {g["calculation_node_id"]: set() for g in equipotential_groups}
    terminal_mapping = []
    device_edges = []
    for component_id, component in sorted(components.items()):
        mapped = [node_map[n] for n in component["terminal_nodes"]]
        active = switch_states.get(component_id, device_states.get(component_id))
        terminal_mapping.append(
            {
                "component_id": component_id,
                "kind": component["kind"],
                "active_for_connectivity": active,
                "terminal_nodes": component["terminal_nodes"],
                "terminal_roles": component.get("terminal_roles"),
                "calculation_terminal_nodes": mapped,
            }
        )
        if component_id in devices and active and len(mapped) == 2:
            a, b = mapped
            adjacency[a].add(b)
            adjacency[b].add(a)
            device_edges.append({"component_id": component_id, "from": a, "to": b})

    remaining = set(adjacency)
    regions = []
    while remaining:
        pending = [min(remaining)]
        reached = set()
        while pending:
            node_id = pending.pop()
            if node_id not in reached:
                reached.add(node_id)
                pending.extend(adjacency[node_id] - reached)
        remaining -= reached
        regions.append(
            {
                "region_id": f"region-{len(regions) + 1:03d}",
                "calculation_node_ids": sorted(reached),
                "engineering_node_ids": sorted(
                    n for n, mapped in node_map.items() if mapped in reached
                ),
            }
        )

    bus_i = node_map["n-220-I"]
    bus_ii = node_map["n-220-II"]
    return {
        "analysis_kind": "connectivity-only",
        "state_origin": "teaching-scenario"
        if teaching
        else "explicit-source-current-states",
        "state_source": state_source or {"origin": "source-draft-current-states"},
        "switch_current_closed": switch_states,
        "device_in_service": device_states,
        "engineering_node_to_calculation_node": node_map,
        "equipotential_groups": equipotential_groups,
        "device_terminal_mapping": terminal_mapping,
        "non_switch_device_edges": device_edges,
        "topological_regions": regions,
        "summary": {
            "equipotential_node_count": len(equipotential_groups),
            "topological_region_count": len(regions),
            "bus_sections_same_equipotential_node": bus_i == bus_ii,
            "transformer_hv_lv_same_equipotential_node": (
                node_map["n-10p5-I"] == node_map["n-T1-hv"]
            ),
        },
        "limitations": [
            "只检查结构连接，不求解潮流、故障电流或稳定性。",
            "连接区域不等于带电区域，也不表示具备可靠供电能力。",
            "等电位节点仅按闭合理想开关形成，不合并变压器和线路本体。",
            "教学开关工况不是图纸实际运行状态，未写回来源草稿。",
            "本草稿省略多个电源和负荷支路，不能代表全厂运行接线。",
        ],
    }


def teaching_scenarios(draft: dict) -> dict[str, dict]:
    """Four explicit artificial scenarios, not inferred drawing operating states."""
    closed = {
        c["component_id"]: True
        for c in draft["components"]
        if c["kind"] in SWITCH_KINDS
    }
    devices_on = {
        c["component_id"]: True
        for c in draft["components"]
        if c["kind"] in DEVICE_KINDS
    }
    scenarios = {
        "all_switches_closed": (None, "全部开关闭合"),
        "section_breaker_open": ("QF-S", "分段断路器 QF-S 断开"),
        "section_disconnector_open": ("QS-S1", "分段隔离开关 QS-S1 断开"),
        "l1_breaker_open": ("QF-L1", "L1 断路器 QF-L1 断开"),
    }
    results = {}
    for scenario_id, (opened_id, label) in scenarios.items():
        states = dict(closed)
        if opened_id is not None:
            states[opened_id] = False
        results[scenario_id] = compile_connectivity(
            draft,
            switch_overrides=states,
            device_overrides=devices_on,
            state_source={
                "origin": "explicit-teaching-assumption",
                "label": label,
                "assumption": "所有 G1/T1/L1 本体投运；除本工况指定开关外，其余八或九个开关均人为设为闭合。",
                "not_from_actual_drawing_state": True,
            },
        )
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    source_bytes = args.source.read_bytes()
    draft = json.loads(source_bytes)
    try:
        compile_connectivity(draft)
    except ConnectivityInputError as exc:
        actual_state_check = {"status": "rejected", "reason": str(exc)}
    else:
        actual_state_check = {"status": "explicit-current-states-available"}
    output = {
        "schema": "EngineeringSwitchConnectivityResult/0.1",
        "analysis_kind": "connectivity-only",
        "case_id": draft["case_id"],
        "source_draft": {
            "path": args.source.resolve().as_posix(),
            "sha256": hashlib.sha256(source_bytes).hexdigest(),
            "original_pdf_sources": draft["sources"],
        },
        "actual_state_check": actual_state_check,
        "scenarios": teaching_scenarios(draft),
        "physical_results_computed": [],
        "not_computed": ["power-flow", "short-circuit", "energization", "stability"],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({k: r["summary"] for k, r in output["scenarios"].items()}))
    print(f"Output: {args.output.resolve()}")


if __name__ == "__main__":
    main()
