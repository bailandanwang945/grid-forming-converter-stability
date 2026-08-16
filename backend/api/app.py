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
from backend.core.average_dq_model import (
    AverageDQModelError,
    STATE_LABELS,
    build_average_dq_model,
    close_port_model_with_external_line,
    compare_with_quasisteady_reduction,
)
from backend.core.average_dq_ablation import (
    AverageDQAblationError,
    ModeMatch,
    run_average_dq_anchor_ablation,
)
from backend.core.average_dq_boundary import (
    AverageDQBoundaryError,
    boundary_study_as_dict,
    run_average_dq_boundary_study,
)
from backend.core.average_dq_presets import (
    ABLATION_PRESET_ID as AVERAGE_DQ_ABLATION_PRESET_ID,
    PRESET_ID as AVERAGE_DQ_PRESET_ID,
    average_dq_ablation_anchor_metadata,
    average_dq_preset_metadata,
    build_average_dq_ablation_anchor_case,
    build_average_dq_verification_case,
)
from backend.core.average_dq_scan import (
    MAX_SCAN_POINTS as MAX_AVERAGE_DQ_SCAN_POINTS,
    AverageDQScanError,
    scan_average_dq_damping_reactance,
)
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
    render_average_dq_report,
    render_fig8_domain_comparison_report,
    render_fig8_report,
    render_reduced_order_report,
)
from backend.domain.network_models import NetworkTopology
from backend.domain.average_dq_models import AverageDQGFMParameters


app = FastAPI(title="构网型变流器稳定性分析平台", version="0.5.0-dev")
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
AverageDQPresetId = Literal["average-dq-smib-verification"]
AverageDQAblationPresetId = Literal[
    "average-dq-hierarchy-disagreement-ablation-v1"
]
AverageDQBoundaryPresetId = Literal[
    "average-dq-hierarchy-disagreement-ablation-v1"
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


class AverageDQAnalysisRequest(BaseModel):
    """Select the verification preset or a complete custom 16-state case."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    preset_id: AverageDQPresetId | None = None
    topology: NetworkTopology | None = None
    parameters: AverageDQGFMParameters | None = None
    simulation_time_s: float = Field(default=2.0, gt=0.0, le=30.0)
    time_step_s: float = Field(default=0.002, ge=0.0001, le=0.1)
    initial_angle_perturbation_rad: float = Field(
        default=1.0e-4, ge=-0.01, le=0.01
    )
    frequency_values_hz: list[float] = Field(
        default_factory=lambda: [0.1, 0.2, 0.5, 1.0, 2.0, 5.0, 10.0, 20.0, 50.0],
        min_length=1,
        max_length=200,
    )

    @model_validator(mode="after")
    def require_one_case_source(self) -> "AverageDQAnalysisRequest":
        has_preset = self.preset_id is not None
        has_custom = self.topology is not None or self.parameters is not None
        if has_preset == has_custom:
            raise ValueError(
                "必须且只能选择 preset_id，或同时给出 topology 与 parameters。"
            )
        if has_custom and (self.topology is None or self.parameters is None):
            raise ValueError("自定义平均值 dq 算例必须同时给出 topology 与 parameters。")
        sample_count = ceil(self.simulation_time_s / self.time_step_s) + 1
        if sample_count > 3001:
            raise ValueError(
                f"非线性时域采样点数 {sample_count} 超过上限 3001；"
                "请缩短仿真时长或增大时间步长。"
            )
        if any(value < 0.0 for value in self.frequency_values_hz):
            raise ValueError("端口导纳频率必须非负。")
        if any(
            right <= left
            for left, right in zip(
                self.frequency_values_hz, self.frequency_values_hz[1:]
            )
        ):
            raise ValueError("端口导纳频率必须严格递增且不得重复。")
        return self


class AverageDQScanRequest(BaseModel):
    """Define a bounded D--line-X scan for one complete average-dq case."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    preset_id: AverageDQPresetId | None = None
    topology: NetworkTopology | None = None
    parameters: AverageDQGFMParameters | None = None
    damping_values_pu: list[float] = Field(
        default_factory=lambda: [10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 80.0],
        min_length=1,
        max_length=MAX_AVERAGE_DQ_SCAN_POINTS,
    )
    reactance_values_pu: list[float] = Field(
        default_factory=lambda: [0.1, 0.2, 0.3, 0.5, 0.8, 1.2],
        min_length=1,
        max_length=MAX_AVERAGE_DQ_SCAN_POINTS,
    )

    @model_validator(mode="after")
    def require_one_case_source(self) -> "AverageDQScanRequest":
        has_preset = self.preset_id is not None
        has_custom = self.topology is not None or self.parameters is not None
        if has_preset == has_custom:
            raise ValueError(
                "必须且只能选择 preset_id，或同时给出 topology 与 parameters。"
            )
        if has_custom and (self.topology is None or self.parameters is None):
            raise ValueError("自定义平均值 dq 扫描必须同时给出 topology 与 parameters。")
        point_count = len(self.damping_values_pu) * len(self.reactance_values_pu)
        if point_count > MAX_AVERAGE_DQ_SCAN_POINTS:
            raise ValueError(
                f"平均值 dq D–X 扫描共 {point_count} 个点，"
                f"超过上限 {MAX_AVERAGE_DQ_SCAN_POINTS}。"
            )
        return self


class AverageDQAblationRequest(BaseModel):
    """Run only the frozen 19-point model-hierarchy ablation experiment."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    preset_id: AverageDQAblationPresetId = AVERAGE_DQ_ABLATION_PRESET_ID


class AverageDQBoundaryRequest(BaseModel):
    """Run only the four frozen one-factor boundary paths."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    preset_id: AverageDQBoundaryPresetId = AVERAGE_DQ_ABLATION_PRESET_ID


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


def _complex_matrix_payload(matrix: np.ndarray) -> list[list[dict[str, float]]]:
    return [
        [
            {"real": float(value.real), "imag": float(value.imag)}
            for value in row
        ]
        for row in matrix
    ]


def _resolve_average_dq_case(
    request: AverageDQAnalysisRequest | AverageDQScanRequest,
) -> tuple[NetworkTopology, AverageDQGFMParameters, dict]:
    if request.preset_id is not None:
        topology, parameters = build_average_dq_verification_case()
        source = {
            "source_kind": "team-defined-average-dq-verification-preset",
            "preset_id": AVERAGE_DQ_PRESET_ID,
            "expected_stability": "stable",
            "paper_fixture": False,
            "physical_hardware_fit": False,
        }
    else:
        if request.topology is None or request.parameters is None:
            raise RuntimeError("平均值 dq 自定义请求缺少拓扑或参数。")
        topology, parameters = request.topology, request.parameters
        source = {
            "source_kind": "user-supplied-average-dq-case",
            "preset_id": None,
            "expected_stability": None,
            "paper_fixture": False,
            "physical_hardware_fit": None,
        }
    return topology, parameters, source


def _average_dq_payload(request: AverageDQAnalysisRequest) -> dict:
    topology, parameters, source = _resolve_average_dq_case(request)
    model = build_average_dq_model(topology, parameters)
    if (
        source["expected_stability"] is not None
        and model.stability.value != source["expected_stability"]
    ):
        raise RuntimeError("平均值 dq 固定预设的稳定性分类与冻结预期不一致。")

    sample_count = ceil(request.simulation_time_s / request.time_step_s) + 1
    times = np.linspace(0.0, request.simulation_time_s, sample_count)
    initial_state = model.operating_point.state.copy()
    initial_state[0] += request.initial_angle_perturbation_rad
    response = model.nonlinear_linear_response(times, initial_state=initial_state)
    admittance = model.port_admittance(request.frequency_values_hz)
    reconstructed = close_port_model_with_external_line(
        model.linearization,
        model.line,
        model.topology.base_values.frequency_hz,
    )
    interconnection_error = float(
        np.max(
            np.abs(
                reconstructed - model.linearization.closed_state_matrix
            )
        )
    )
    reduction = compare_with_quasisteady_reduction(model)
    dominant_index = max(
        range(model.poles_per_s.size),
        key=lambda index: (
            model.poles_per_s[index].real,
            model.poles_per_s[index].imag,
        ),
    )
    dominant_per_s = model.poles_per_s[dominant_index]
    dominant_hz = model.poles_hz[dominant_index]
    operating = model.operating_point
    return {
        "run_id": f"average-dq-{topology.id}",
        "status": "completed",
        "analysis_mode": "transparent-average-value-dq-smib-v1",
        "input_topology": topology.model_dump(mode="json"),
        "input_parameters": parameters.model_dump(mode="json"),
        "input_validation": {
            "status": "passed",
            "network_contract": f"NetworkTopology/{topology.schema_version}",
            "parameter_contract": (
                f"AverageDQGFMParameters/{parameters.schema_version}"
            ),
            "frame_convention_id": topology.frame_convention_id,
            "scope_validation": "single-vsm-single-rl-line-infinite-bus-passed",
        },
        "operating_point": {
            "state_labels": list(STATE_LABELS),
            "state": operating.state.tolist(),
            "grid_voltage_global_pu": operating.grid_voltage_global.tolist(),
            "pcc_voltage_local_pu": operating.pcc_voltage_local.tolist(),
            "pcc_voltage_global_pu": operating.pcc_voltage_global.tolist(),
            "algebraic_residual": operating.algebraic_residual.tolist(),
            "closed_rhs_residual_inf": operating.closed_rhs_residual_inf,
            "device_rhs_residual_inf": operating.device_rhs_residual_inf,
            "active_power_balance_residual_pu": (
                operating.active_power_balance_residual_pu
            ),
            "converter_current_magnitude_pu": (
                operating.converter_current_magnitude_pu
            ),
            "grid_current_magnitude_pu": operating.grid_current_magnitude_pu,
            "internal_voltage_magnitude_pu": (
                operating.internal_voltage_magnitude_pu
            ),
        },
        "result": {
            "stability": model.stability.value,
            "stability_tolerance_per_s": model.stability_tolerance_per_s,
            "closed_state_matrix": (
                model.linearization.closed_state_matrix.tolist()
            ),
            "poles": [
                _complex_pole_payload(pole_per_s, pole_hz)
                for pole_per_s, pole_hz in zip(
                    model.poles_per_s, model.poles_hz, strict=True
                )
            ],
            "dominant_mode": {
                **_complex_pole_payload(dominant_per_s, dominant_hz),
                "oscillation_frequency_hz": (
                    abs(float(dominant_per_s.imag)) / (2.0 * np.pi)
                ),
            },
            "port_interconnection_max_abs_error": interconnection_error,
            "quasisteady_reduction_comparison": {
                "synchronizing_stiffness_pu_per_rad": (
                    reduction.synchronizing_stiffness_pu_per_rad
                ),
                "reduced_state_matrix": reduction.reduced_state_matrix.tolist(),
                "reduced_poles": [
                    _complex_pole_payload(pole, pole / (2.0 * np.pi))
                    for pole in reduction.reduced_poles_per_s
                ],
                "full_dominant_pole": _complex_pole_payload(
                    reduction.full_dominant_pole_per_s,
                    reduction.full_dominant_pole_per_s / (2.0 * np.pi),
                ),
                "reduced_dominant_pole": _complex_pole_payload(
                    reduction.reduced_dominant_pole_per_s,
                    reduction.reduced_dominant_pole_per_s / (2.0 * np.pi),
                ),
                "matched_full_pole": _complex_pole_payload(
                    reduction.matched_full_pole_per_s,
                    reduction.matched_full_pole_per_s / (2.0 * np.pi),
                ),
                "oscillation_frequency_relative_error": (
                    reduction.oscillation_frequency_relative_error
                ),
                "decay_rate_relative_error": reduction.decay_rate_relative_error,
                "real_part_relative_error": reduction.real_part_relative_error,
                "matching_method": reduction.matching_method,
                "interpretation": (
                    "三状态模型使用同一工作点的准稳态 Q–V 关系求得 Kδ；"
                    "稳定性分类分别取两层模型的最右极点，误差则比较三状态最右模态与"
                    "16状态模型中最邻近的正虚部同步模态；该匹配不证明一般等价。"
                ),
            },
            "port_admittance": {
                "current_direction": "network-to-device-positive",
                "voltage_frame": "global-synchronous-dq",
                "frequencies_hz": request.frequency_values_hz,
                "matrices": [
                    _complex_matrix_payload(matrix) for matrix in admittance
                ],
            },
            "time_response": {
                "response_kind": "nonlinear-vs-local-linear-initial-condition",
                "time_s": response.time_s.tolist(),
                "state_labels": list(response.state_labels),
                "initial_state": initial_state.tolist(),
                "nonlinear_states": response.nonlinear_states.tolist(),
                "linear_states": response.linear_states.tolist(),
            },
        },
        "model_scope": {
            "claim_level": "average-value-positive-sequence-smib-model-only",
            "statement": (
                "该结果属于团队定义的16状态平均值 dq 单机模型；它比三状态低频模型"
                "保留更多控制与电磁动态，但不是论文 Fig. 8 模型、PWM 开关模型、"
                "电磁暂态真值或任意多机构网系统结论。"
            ),
            "retained_dynamics": [
                "LCL-filter-electromagnetic-dynamics",
                "cascaded-dq-voltage-current-PI-control",
                "VSM-active-power-frequency-loop",
                "reactive-power-voltage-droop",
                "first-order-average-modulator",
                "external-series-RL-line",
            ],
            "excluded_dynamics": [
                "PWM-switching-ripple",
                "dc-link-and-prime-mover-dynamics",
                "current-limiting-and-anti-windup",
                "fault-ride-through-and-mode-switching",
                "unbalance-zero-sequence-and-harmonics",
                "static-load-algebraic-constraints",
                "multi-converter-nonlinear-DAE",
            ],
        },
        "provenance": {
            "implementation": "backend.core.average_dq_model",
            "model_specification": (
                "docs/specs/models/average-dq-gfm-v1-proposal.md"
            ),
            "verification_basis": [
                "analytic-no-load-equilibrium",
                "steady-state-active-power-balance",
                "global-frame-rotation-invariance",
                "finite-difference-jacobian-convergence",
                "nonlinear-linear-small-signal-agreement",
                "port-line-direct-closure-matrix-agreement",
                "working-point-matched-three-state-dominant-mode-comparison",
            ],
            "separated_from_fig8_fixture": True,
            **source,
        },
    }


def _average_dq_scan_payload(request: AverageDQScanRequest) -> dict:
    topology, parameters, source = _resolve_average_dq_case(request)
    scan = scan_average_dq_damping_reactance(
        topology,
        parameters,
        damping_values_pu=request.damping_values_pu,
        reactance_values_pu=request.reactance_values_pu,
    )
    return {
        "run_id": f"average-dq-scan-{topology.id}",
        "status": "completed",
        "analysis_mode": "average-dq-full-vs-matched-reduction-d-x-scan-v1",
        "input_topology": topology.model_dump(mode="json"),
        "input_parameters": parameters.model_dump(mode="json"),
        "result": scan.as_dict(),
        "model_scope": {
            "statement": (
                "逐点重算16状态正序平均值 dq 单机模型，并与同一工作点匹配的"
                "三状态近似比较。线路 X 是所选外部支路标幺电抗，不等同于普遍 SCR。"
            ),
            "interpretation": (
                "分类分别由两层模型各自最右极点确定；频率与实部误差只比较"
                "三状态最右模态和16状态中最邻近的正虚部模态。分类不一致说明"
                "低频近似遗漏了改变稳定性结论的额外模态，但参与因子只作模态诊断，"
                "不单独构成因果证明，也不是论文小增益—小相位定理的反例。"
            ),
            "paper_theorem_evaluated": False,
            "physical_validation": False,
        },
        "provenance": {
            **source,
            "implementation": "backend.core.average_dq_scan",
            "point_calculation": "fresh-workpoint-and-central-difference-linearization",
            "interpolation_used": False,
        },
    }


def _mode_match_payload(match: ModeMatch) -> dict:
    """Serialize a tracked mode without overstating local matching evidence."""

    return {
        "pole": _complex_pole_payload(
            match.eigenvalue_per_s,
            match.eigenvalue_per_s / (2.0 * np.pi),
        ),
        "reference_pole": _complex_pole_payload(
            match.reference_eigenvalue_per_s,
            match.reference_eigenvalue_per_s / (2.0 * np.pi),
        ),
        "status": match.status,
        "reason": match.reason,
        "path_label": match.path_label,
        "cumulative_tracking_steps": match.path_steps,
        "minimum_step_right_mac": match.right_mac,
        "minimum_step_left_mac": match.left_mac,
        "minimum_step_combined_mac": match.combined_mac,
        "maximum_step_normalized_eigenvalue_distance": (
            match.normalized_distance
        ),
        "minimum_step_confidence": match.confidence,
        "maximum_step_second_candidate_confidence": (
            match.second_best_confidence
        ),
        "minimum_step_local_candidate_margin": (
            match.relative_confidence_margin
        ),
        "maximum_eigenvalue_condition_number": match.condition_number,
        "maximum_right_eigenpair_residual": match.right_residual,
        "maximum_left_eigenpair_residual": match.left_residual,
        "thresholds": {
            "minimum_individual_mac": (
                match.minimum_individual_mac_threshold
            ),
            "maximum_normalized_eigenvalue_distance": (
                match.maximum_normalized_distance_threshold
            ),
            "maximum_eigenvalue_condition_number": (
                match.maximum_condition_number_threshold
            ),
            "maximum_eigenpair_residual": (
                match.maximum_eigenpair_residual_threshold
            ),
            "minimum_local_candidate_margin": (
                match.minimum_relative_margin_threshold
            ),
        },
        "candidate_index_is_internal_only": True,
    }


def _average_dq_ablation_payload(request: AverageDQAblationRequest) -> dict:
    topology, parameters = build_average_dq_ablation_anchor_case()
    study = run_average_dq_anchor_ablation(topology, parameters)
    points = list(study.points)
    stability_counts = {
        label: sum(point.stability == label for point in points)
        for label in ("stable", "marginal", "unstable")
    }

    extra_tracking_counts = {
        label: sum(point.extra_mode.status == label for point in points)
        for label in ("matched", "pending")
    }
    synchronous_tracking_counts = {
        label: sum(point.synchronous_mode.status == label for point in points)
        for label in ("matched", "pending")
    }
    serialized_points = []
    for point in points:
        serialized_points.append(
            {
                "scenario_id": point.scenario_id,
                "factors": dict(point.factors),
                "damping_coefficient_pu": point.damping_coefficient_pu,
                "line_reactance_pu": point.line_reactance_pu,
                "stability": point.stability,
                "rightmost_pole": _complex_pole_payload(
                    point.rightmost_pole_per_s,
                    point.rightmost_pole_per_s / (2.0 * np.pi),
                ),
                "poles": [
                    _complex_pole_payload(pole, pole / (2.0 * np.pi))
                    for pole in point.poles_per_s
                ],
                "extra_mode": _mode_match_payload(point.extra_mode),
                "synchronous_mode": _mode_match_payload(
                    point.synchronous_mode
                ),
                "extra_group_participation": dict(
                    point.extra_group_participation
                ),
                "synchronous_group_participation": dict(
                    point.synchronous_group_participation
                ),
                "reduced_poles": [
                    _complex_pole_payload(pole, pole / (2.0 * np.pi))
                    for pole in point.reduced_poles_per_s
                ],
                "reduced_dominant_pole": _complex_pole_payload(
                    point.reduced_dominant_pole_per_s,
                    point.reduced_dominant_pole_per_s / (2.0 * np.pi),
                ),
                "synchronizing_stiffness_pu_per_rad": (
                    point.synchronizing_stiffness_pu_per_rad
                ),
                "synchronous_frequency_relative_error": (
                    point.synchronous_frequency_relative_error
                ),
                "synchronous_decay_relative_error": (
                    point.synchronous_decay_relative_error
                ),
                "residuals": {
                    "algebraic_inf": point.residuals.algebraic_inf,
                    "closed_rhs_inf": point.residuals.closed_rhs_inf,
                    "device_rhs_inf": point.residuals.device_rhs_inf,
                    "active_power_balance_abs_pu": (
                        point.residuals.active_power_balance_abs_pu
                    ),
                },
            }
        )
    return {
        "run_id": f"average-dq-ablation-{request.preset_id}",
        "status": "completed",
        "analysis_mode": "fixed-average-dq-modal-continuation-ablation-v1",
        "preset_id": request.preset_id,
        "fixed_anchor": {
            "damping_coefficient_pu": 60.0,
            "external_line_reactance_pu": 0.1,
            "state_definition": "fixed-16-state-per-unit-and-delta-rad-basis",
        },
        "result": {
            "point_count": study.point_count,
            "summary": {
                "stability_counts": stability_counts,
                "extra_mode_tracking_counts": extra_tracking_counts,
                "synchronous_mode_tracking_counts": (
                    synchronous_tracking_counts
                ),
            },
            "baseline_extra_mode": _complex_pole_payload(
                study.baseline_extra_mode_per_s,
                study.baseline_extra_mode_per_s / (2.0 * np.pi),
            ),
            "baseline_synchronous_mode": _complex_pole_payload(
                study.baseline_synchronous_mode_per_s,
                study.baseline_synchronous_mode_per_s / (2.0 * np.pi),
            ),
            "state_scaling": dict(study.state_scaling),
            "state_scaling_scope": study.state_scaling_scope,
            "points": serialized_points,
        },
        "model_scope": {
            "claim_level": "fixed-team-average-dq-ablation-only",
            "statement": (
                "该实验只属于团队定义的16状态平均值 dq 单机模型及其固定19个"
                "端点工况；整体稳定性由各工况最右极点独立判定，命名模态另经"
                "连续追踪核对。"
            ),
            "tracking_method": (
                "完整谱一对一指派，结合左右特征向量 MAC、归一化特征值距离、"
                "简单特征值条件数、左右特征对残差和局部候选间隔；门槛不满足时"
                "沿参数路径二分加密。双 PI 角点按两种参数调整顺序复核。"
            ),
            "tracking_boundary": (
                "局部候选间隔不是全局指派唯一性证明；参与度只作当前固定状态"
                "坐标下的模态诊断。19点结果不证明唯一因果、全参数域单调性、"
                "硬件或电磁暂态系统稳定性。"
            ),
            "paper_theorem_evaluated": False,
            "physical_validation": False,
            "causal_identification": False,
            "accepts_arbitrary_state_definition": False,
        },
        "provenance": {
            **average_dq_ablation_anchor_metadata(),
            "implementation": "backend.core.average_dq_ablation",
            "point_calculation": (
                "fresh-workpoint-and-central-difference-linearization"
            ),
            "full_spectrum_assignment": "hungarian-linear-assignment",
            "adaptive_continuation_refinement": True,
            "interpolation_used_for_reported_points": False,
        },
    }


def _average_dq_boundary_payload(request: AverageDQBoundaryRequest) -> dict:
    topology, parameters = build_average_dq_ablation_anchor_case()
    study = run_average_dq_boundary_study(topology, parameters)
    return {
        "run_id": f"average-dq-boundary-{request.preset_id}",
        "status": "completed",
        "analysis_mode": "fixed-average-dq-one-factor-boundary-continuation-v1",
        "preset_id": request.preset_id,
        "result": boundary_study_as_dict(study),
        "model_scope": {
            "claim_level": "fixed-team-average-dq-one-factor-boundaries-only",
            "statement": (
                "从固定19点消融中四个稳定化端点出发，分别沿单因素路径求解"
                "被追踪附加模态实部过零和完整16状态谱横坐标过零；二者独立"
                "计算并报告模态交接。"
            ),
            "tracking_boundary": study.interpretation_boundary,
            "paper_theorem_evaluated": False,
            "physical_validation": False,
            "causal_identification": False,
            "accepts_arbitrary_parameter_paths": False,
        },
        "provenance": {
            **average_dq_ablation_anchor_metadata(),
            "implementation": "backend.core.average_dq_boundary",
            "point_calculation": (
                "fresh-workpoint-and-central-difference-linearization"
            ),
            "continuation": "adaptive-modal-tracking-plus-log-bisection",
            "interpolation_used_for_reported_boundaries": False,
        },
    }


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "service": "gfm-stability-api", "version": "0.5.0-dev"}


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


@app.get("/api/average-dq/presets")
def average_dq_presets() -> dict:
    return {
        "analysis_mode": "transparent-average-value-dq-smib-v1",
        "separation_notice": (
            "该预设为团队定义的16状态模型校核算例，不属于论文 Fig. 8 作者模型。"
        ),
        "claim_level": "average-value-positive-sequence-smib-model-only",
        "presets": [average_dq_preset_metadata()],
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


@app.post("/api/average-dq/analyze")
def run_average_dq_analysis(request: AverageDQAnalysisRequest) -> dict:
    try:
        return _average_dq_payload(request)
    except AverageDQModelError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except RuntimeError as error:
        raise HTTPException(status_code=500, detail=str(error)) from error


@app.post("/api/average-dq/scan")
def run_average_dq_scan(request: AverageDQScanRequest) -> dict:
    try:
        return _average_dq_scan_payload(request)
    except (AverageDQScanError, AverageDQModelError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except RuntimeError as error:
        raise HTTPException(status_code=500, detail=str(error)) from error


@app.post("/api/average-dq/ablation")
def run_average_dq_ablation(request: AverageDQAblationRequest) -> dict:
    try:
        return _average_dq_ablation_payload(request)
    except (AverageDQAblationError, AverageDQModelError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except RuntimeError as error:
        raise HTTPException(status_code=500, detail=str(error)) from error


@app.post("/api/average-dq/boundary")
def run_average_dq_boundary(request: AverageDQBoundaryRequest) -> dict:
    try:
        return _average_dq_boundary_payload(request)
    except (
        AverageDQBoundaryError,
        AverageDQAblationError,
        AverageDQModelError,
    ) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except RuntimeError as error:
        raise HTTPException(status_code=500, detail=str(error)) from error


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


@app.post("/api/reports/average-dq", response_class=HTMLResponse)
def average_dq_report(request: AverageDQAnalysisRequest) -> str:
    """Return the same average-dq calculation as a self-contained HTML report."""

    try:
        return render_average_dq_report(_average_dq_payload(request))
    except AverageDQModelError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except RuntimeError as error:
        raise HTTPException(status_code=500, detail=str(error)) from error
