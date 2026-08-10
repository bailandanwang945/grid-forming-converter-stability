from __future__ import annotations

import json
from math import ceil
from typing import Literal

import numpy as np
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, ConfigDict, Field, model_validator

from backend.core.fig8_kernel import available_fig8_cases, evaluate_fig8_case
from backend.core.fig8_domain_comparison import load_fig8_domain_comparison
from backend.core.reduced_order_model import (
    ReducedOrderModelError,
    build_reduced_order_model,
)
from backend.core.reduced_order_presets import (
    available_reduced_order_presets,
    get_reduced_order_preset,
)
from backend.core.reduced_order_scan import (
    MAX_SCAN_POINTS,
    ReducedOrderScanError,
    scan_damping_reactance,
)
from backend.core.reporting import (
    render_fig8_domain_comparison_report,
    render_fig8_report,
    render_reduced_order_report,
)
from backend.domain.network_models import NetworkTopology


app = FastAPI(title="构网型变流器稳定性分析平台", version="0.3.0-rc3")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


Fig8CaseId = Literal["fig8_D_0p05", "fig8_D_0p5"]
ReducedOrderPresetId = Literal[
    "reduced-smib-stable",
    "reduced-smib-critical",
    "reduced-smib-unstable",
]


class AnalysisRequest(BaseModel):
    """Select one of the two version-pinned author-fixture cases."""

    model_config = ConfigDict(extra="forbid")

    scenario_id: Fig8CaseId = "fig8_D_0p5"


class ReducedOrderAnalysisRequest(BaseModel):
    """Select exactly one reduced-order preset or validated custom topology."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    preset_id: ReducedOrderPresetId | None = None
    topology: NetworkTopology | None = None
    simulation_time_s: float = Field(default=20.0, gt=0.0, le=300.0)
    time_step_s: float = Field(default=0.02, ge=0.001, le=1.0)
    initial_angle_perturbation_rad: float = Field(
        default=1.0e-3,
        ge=-0.1,
        le=0.1,
    )

    @model_validator(mode="after")
    def require_one_topology_source(self) -> "ReducedOrderAnalysisRequest":
        selected_sources = int(self.preset_id is not None) + int(
            self.topology is not None
        )
        if selected_sources != 1:
            raise ValueError("必须且只能选择一个 preset_id 或 topology。")
        sample_count = ceil(self.simulation_time_s / self.time_step_s) + 1
        if sample_count > 5001:
            raise ValueError(
                f"时域响应采样点数 {sample_count} 超过上限 5001；"
                "请缩短仿真时长或增大时间步长。"
            )
        return self


class ReducedOrderScanRequest(BaseModel):
    """Define an explicit bounded D--X grid for one VSM and one AC line."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    topology: NetworkTopology
    target_vsm_id: str = Field(min_length=1, max_length=64)
    target_line_id: str = Field(min_length=1, max_length=64)
    damping_values_pu: list[float] = Field(min_length=1, max_length=MAX_SCAN_POINTS)
    reactance_values_pu: list[float] = Field(
        min_length=1,
        max_length=MAX_SCAN_POINTS,
    )

    @model_validator(mode="after")
    def limit_grid_size(self) -> "ReducedOrderScanRequest":
        point_count = len(self.damping_values_pu) * len(self.reactance_values_pu)
        if point_count > MAX_SCAN_POINTS:
            raise ValueError(
                f"D–X 扫描网格共 {point_count} 个点，超过上限 {MAX_SCAN_POINTS}。"
            )
        return self


def _analysis_payload(request: AnalysisRequest) -> dict:
    result = evaluate_fig8_case(request.scenario_id)
    return {
        "run_id": f"portable-{request.scenario_id}",
        "scenario_id": request.scenario_id,
        "status": "completed",
        "summary": {
            "closed_loop_reference": result["closed_loop_reference"],
            "criterion_status": result["sampled_band_status"],
            "dominant_pole_hz": result["dominant_pole_hz"],
            "uncovered_points": result["counts"]["uncovered"],
            "indeterminate_points": result["counts"]["indeterminate_coverage"],
            "frequency_points": len(result["frequency_scan"]["frequencies_hz"]),
            "theorem_status": result["theorem_status"],
            "screening_counts": result["counts"],
            "paper_reported_oscillation_hz": 1.2,
            "reproduced_dominant_oscillation_hz": result["dominant_pole_hz"]["imag"],
            "frequency_discrepancy_status": "unresolved",
        },
        "frequency_scan": result["frequency_scan"],
        "phase_seed": result["phase_seed"],
        "provenance": {
            **result["provenance"],
            "mode": "portable-pinned-author-fixture",
            "paper_case": "Cifelli–Anta Fig. 8",
            "interpretation": result["interpretation_boundary"],
        },
    }


def _complex_pole_payload(pole_per_s: complex, pole_hz: complex) -> dict:
    return {
        "real_per_s": float(pole_per_s.real),
        "imag_per_s": float(pole_per_s.imag),
        "real_hz": float(pole_hz.real),
        "imag_hz": float(pole_hz.imag),
    }


def _reduced_order_payload(request: ReducedOrderAnalysisRequest) -> dict:
    preset = (
        get_reduced_order_preset(request.preset_id)
        if request.preset_id is not None
        else None
    )
    topology = preset.build_topology() if preset is not None else request.topology
    if topology is None:  # Kept as an internal invariant after request validation.
        raise RuntimeError("低频降阶模型请求缺少拓扑。")

    model = build_reduced_order_model(topology)
    expected_stability = preset.expected_stability if preset is not None else None
    if expected_stability is not None and model.stability.value != expected_stability:
        raise RuntimeError(
            f"预设 {preset.id!r} 的计算分类 {model.stability.value!r} "
            f"与固定预期 {expected_stability!r} 不一致。"
        )

    sample_count = ceil(request.simulation_time_s / request.time_step_s) + 1
    times = np.linspace(0.0, request.simulation_time_s, sample_count)
    initial_state = np.zeros(model.state_matrix.shape[0], dtype=np.float64)
    initial_state[0] = request.initial_angle_perturbation_rad
    response = model.linear_time_response(times, initial_state=initial_state)

    if preset is not None:
        source = {
            "source_kind": "team-defined-analytic-verification-preset",
            "preset_id": preset.id,
            "expected_stability": preset.expected_stability,
            "expected_stability_match": True,
            **preset.provenance(),
        }
    else:
        source = {
            "source_kind": "user-supplied-network-topology",
            "preset_id": None,
            "expected_stability": None,
            "expected_stability_match": None,
            "paper_fixture": False,
        }

    return {
        "run_id": f"reduced-order-{topology.id}",
        "status": "completed",
        "analysis_mode": "low-frequency-angle-frequency-active-power-reduced-order",
        "input_topology": topology.model_dump(mode="json"),
        "input_validation": {
            "status": "passed",
            "network_contract": f"NetworkTopology/{topology.schema_version}",
            "topology_id": topology.id,
            "frame_convention_id": topology.frame_convention_id,
            "reference_bus_id": topology.reference_bus_id,
            "connected_network": True,
            "core_scope_validation": "passed",
            "entity_counts": {
                "buses": len(topology.buses),
                "lines": len(topology.lines),
                "grid_forming_converters": len(
                    topology.grid_forming_converters
                ),
                "infinite_buses": len(topology.infinite_buses),
                "loads": len(topology.loads),
            },
        },
        "result": {
            "stability": model.stability.value,
            "stability_tolerance_per_s": model.stability_tolerance_per_s,
            "vsm_ids": list(model.vsm_ids),
            "state_labels": list(model.state_labels),
            "state_matrix": model.state_matrix.tolist(),
            "synchronous_stiffness_matrix": (
                model.synchronous_stiffness_matrix.tolist()
            ),
            "poles": [
                _complex_pole_payload(pole_per_s, pole_hz)
                for pole_per_s, pole_hz in zip(
                    model.poles_per_s,
                    model.poles_hz,
                    strict=True,
                )
            ],
            "dominant_mode": {
                **_complex_pole_payload(
                    model.dominant_mode.eigenvalue_per_s,
                    model.dominant_mode.pole_hz,
                ),
                "oscillation_frequency_hz": (
                    model.dominant_mode.oscillation_frequency_hz
                ),
                "damping_ratio": model.dominant_mode.damping_ratio,
            },
            "time_response": {
                "response_kind": "zero-input-initial-condition",
                "time_s": response.time_s.tolist(),
                "state_labels": list(response.state_labels),
                "states": response.states.tolist(),
                "initial_state": initial_state.tolist(),
            },
        },
        "model_scope": {
            "claim_level": "low-frequency-reduced-order-model-only",
            "statement": (
                "该结果仅说明所给角度—频率—有功测量降阶模型的线性化特征；"
                "不等同于论文完整定理复现，也不构成任意构网型变流器的稳定性结论。"
            ),
            "assumptions": list(model.assumptions),
            "used_input_fields": [
                "base_values.frequency_hz",
                "buses[].id",
                "lines[].from_bus_id/to_bus_id/reactance_pu",
                "grid_forming_converters[].id/bus_id/control_mode/virtual_inertia_s/damping_coefficient_pu/active_power_measurement_time_constant_s",
                "infinite_buses[].bus_id",
                "reference_bus_id",
            ],
            "validated_but_unused_input_fields": [
                "base_values.apparent_power_va/voltage_v",
                "buses[].name/nominal_voltage_v",
                "lines[].name/resistance_pu/shunt_susceptance_pu",
                "grid_forming_converters[].name/rated_apparent_power_va/active_power_setpoint_pu/reactive_power_setpoint_pu/voltage_setpoint_pu",
                "infinite_buses[].name/voltage_magnitude_pu/voltage_angle_deg",
                "loads[]",
            ],
            "excluded_dynamics": [
                "line-resistance-in-active-power-stiffness",
                "reactive-power-voltage-coupling",
                "converter-inner-loops",
                "saturation-and-current-limits",
                "electromagnetic-transients",
                "static-load-operating-point-effects",
            ],
        },
        "provenance": {
            "implementation": "backend.core.reduced_order_model",
            "topology_contract": "backend.domain.network_models.NetworkTopology",
            "separated_from_fig8_fixture": True,
            **source,
        },
    }


def _reduced_order_scan_payload(request: ReducedOrderScanRequest) -> dict:
    scan = scan_damping_reactance(
        request.topology,
        target_vsm_id=request.target_vsm_id,
        target_line_id=request.target_line_id,
        damping_values_pu=request.damping_values_pu,
        reactance_values_pu=request.reactance_values_pu,
    )
    return {
        "run_id": (
            f"reduced-order-dx-scan-{request.topology.id}-"
            f"{request.target_vsm_id}-{request.target_line_id}"
        ),
        "status": "completed",
        "analysis_mode": "low-frequency-reduced-order-damping-reactance-plane",
        "input_topology": request.topology.model_dump(mode="json"),
        "scan": scan.as_dict(),
        "model_scope": {
            "claim_level": "low-frequency-reduced-order-model-only",
            "parameter_plane": "selected-vsm-damping-D-by-selected-line-reactance-X",
            "line_reactance_interpretation": (
                "X 是所选交流线路在算例基准值下的标幺电抗；"
                "本接口不把 X 自动换算或命名为短路比 SCR。"
            ),
            "statement": (
                "每个网格点均重新构造角度—频率—有功测量降阶状态矩阵并计算特征根；"
                "所得参数平面不是论文小增益—小相位判据的评价结果，"
                "也不是 SCR 与任意构网型变流器稳定性的普遍关系。"
            ),
        },
        "provenance": {
            "implementation": "backend.core.reduced_order_scan.scan_damping_reactance",
            "point_solver": "backend.core.reduced_order_model.build_reduced_order_model",
            "topology_contract": "backend.domain.network_models.NetworkTopology/1.0",
            "grid_is_explicit_not_interpolated": True,
            "input_topology_mutated": False,
            "separated_from_fig8_fixture": True,
        },
    }


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "service": "gfm-stability-api", "version": "0.3.0-rc3"}


@app.get("/api/scenarios")
def scenarios() -> dict:
    return {
        "scenarios": [
            {
                "id": case["case_id"],
                "name": f"论文 Fig. 8：{case['label']}",
                "description": (
                    f"作者工作簿固定夹具，VSM 阻尼 D={case['damping']:.2f}；"
                    "由便携式 Python 内核重新计算，不使用人工预览曲线。"
                ),
                "analysis_mode": "portable-pinned-author-fixture",
                "damping": case["damping"],
            }
            for case in available_fig8_cases()
        ]
    }


@app.get("/api/reduced-order/presets")
def reduced_order_presets() -> dict:
    return {
        "analysis_mode": "low-frequency-angle-frequency-active-power-reduced-order",
        "separation_notice": (
            "以下预设为团队定义的解析校核算例，不属于论文 Fig. 8 作者固定夹具。"
        ),
        "claim_level": "low-frequency-reduced-order-model-only",
        "presets": [
            {
                "id": preset.id,
                "name": preset.name,
                "description": preset.description,
                "expected_stability": preset.expected_stability,
                "topology": preset.build_topology().model_dump(mode="json"),
                "provenance": preset.provenance(),
            }
            for preset in available_reduced_order_presets()
        ],
    }


@app.post("/api/analysis/run")
def run_analysis(request: AnalysisRequest) -> dict:
    try:
        return _analysis_payload(request)
    except (ValueError, RuntimeError, OSError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@app.get("/api/comparison/fig8-domain")
def fig8_domain_comparison() -> dict:
    """Return frozen same-model D--SCR comparison evidence."""

    try:
        return load_fig8_domain_comparison()
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as error:
        raise HTTPException(status_code=500, detail=str(error)) from error


@app.post("/api/reduced-order/analyze")
def run_reduced_order_analysis(request: ReducedOrderAnalysisRequest) -> dict:
    try:
        return _reduced_order_payload(request)
    except ReducedOrderModelError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except RuntimeError as error:
        raise HTTPException(status_code=500, detail=str(error)) from error


@app.post("/api/reduced-order/scan")
def run_reduced_order_scan(request: ReducedOrderScanRequest) -> dict:
    try:
        return _reduced_order_scan_payload(request)
    except (ReducedOrderScanError, ReducedOrderModelError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@app.get("/api/reports/fig8", response_class=HTMLResponse)
def fig8_report(scenario_id: Fig8CaseId = "fig8_D_0p5") -> str:
    return render_fig8_report(_analysis_payload(AnalysisRequest(scenario_id=scenario_id)))


@app.get("/api/reports/fig8-domain", response_class=HTMLResponse)
def fig8_domain_comparison_report() -> str:
    return render_fig8_domain_comparison_report(load_fig8_domain_comparison())


@app.post("/api/reports/reduced-order", response_class=HTMLResponse)
def reduced_order_report(request: ReducedOrderAnalysisRequest) -> str:
    """Return a self-contained report from the same validated analysis path."""

    try:
        return render_reduced_order_report(_reduced_order_payload(request))
    except ReducedOrderModelError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except RuntimeError as error:
        raise HTTPException(status_code=500, detail=str(error)) from error
