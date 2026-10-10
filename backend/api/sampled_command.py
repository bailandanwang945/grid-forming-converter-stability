"""Opt-in experimental sampled-command comparisons; existing analysis is unchanged."""

from __future__ import annotations

import json
from math import isfinite
from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Request
from fastapi.routing import APIRoute
from pydantic import BaseModel, ConfigDict, Field, model_validator

from backend.core.average_dq_model import build_average_dq_model
from backend.core.average_dq_presets import build_average_dq_verification_case
from backend.domain.average_dq_models import AverageDQGFMParameters
from backend.domain.network_models import NetworkTopology


class StandardJsonRoute(APIRoute):
    """Reject non-JSON numeric constants before validation-error serialization.

    Otherwise an error containing NaN/Infinity can itself fail JSON encoding.
    This guard is local to this opt-in router, not a global error-handler change.
    """

    def get_route_handler(self):
        original_handler = super().get_route_handler()

        def reject_constant(_value):
            raise ValueError("nonstandard JSON number")

        def finite_float(value):
            parsed = float(value)
            if not isfinite(parsed):
                raise ValueError("JSON number exceeds finite float range")
            return parsed

        async def standard_json_handler(request: Request):
            body = await request.body()
            if len(body) > 2 * 1024 * 1024:
                raise HTTPException(
                    status_code=413, detail="试验接口的请求体不得超过2 MiB。"
                )
            if body:
                try:
                    parsed = json.loads(
                        body, parse_constant=reject_constant, parse_float=finite_float
                    )
                    stack = [(parsed, 0)]
                    while stack:
                        value, depth = stack.pop()
                        if depth > 32:
                            raise ValueError("JSON nesting exceeds the supported depth")
                        if isinstance(value, dict):
                            stack.extend((child, depth + 1) for child in value.values())
                        elif isinstance(value, list):
                            stack.extend((child, depth + 1) for child in value)
                except (ValueError, UnicodeDecodeError, RecursionError) as error:
                    raise HTTPException(
                        status_code=422,
                        detail="输入须为标准JSON；数值必须有限，编码和嵌套层数须在支持范围内。",
                    ) from error
            return await original_handler(request)

        return standard_json_handler


router = APIRouter(
    prefix="/api/experimental/average-dq",
    tags=["试验性模型对照"],
    route_class=StandardJsonRoute,
)
HoldingFrame = Literal["local-control-dq", "global-synchronous-dq"]
SamplingPeriod = Annotated[float, Field(strict=True, ge=1.0e-7, le=0.02)]
DelaySteps = Annotated[int, Field(strict=True, ge=0, le=1)]


class SampledCommandRequest(BaseModel):
    """A complete supported average-dq case with explicitly selected assumptions.

    Period limits bound this numerical service; they are not safe device settings.
    No time-response or frequency-grid fields are accepted or silently ignored.
    """

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    preset_id: Literal["average-dq-smib-verification"] | None = None
    topology: NetworkTopology | None = None
    parameters: AverageDQGFMParameters | None = None
    sampling_periods_s: list[SamplingPeriod] = Field(
        default_factory=lambda: [1e-4, 5e-4, 1e-3, 2e-3], min_length=1, max_length=16
    )
    holding_frames: list[HoldingFrame] = Field(
        default_factory=lambda: ["local-control-dq", "global-synchronous-dq"],
        min_length=1,
        max_length=2,
    )
    delay_steps: list[DelaySteps] = Field(
        default_factory=lambda: [0, 1], min_length=1, max_length=2
    )

    @model_validator(mode="after")
    def validate_case_and_grid(self) -> "SampledCommandRequest":
        has_preset = self.preset_id is not None
        has_custom = self.topology is not None or self.parameters is not None
        if has_preset == has_custom:
            raise ValueError(
                "必须选择一个预置算例，或同时提交完整拓扑与平均值模型参数。"
            )
        if has_custom and (self.topology is None or self.parameters is None):
            raise ValueError("自定义算例须同时提供 topology 与 parameters。")
        for name in ("sampling_periods_s", "holding_frames", "delay_steps"):
            values = getattr(self, name)
            if len(set(values)) != len(values):
                raise ValueError(f"{name} 不得重复。")
        if any(
            right <= left
            for left, right in zip(self.sampling_periods_s, self.sampling_periods_s[1:])
        ):
            raise ValueError("采样周期须严格递增。")
        return self


@router.post(
    "/sampled-command",
    summary="指令采样保持与连续调制近似对照（试验性）",
    description=(
        "对同一单机平均值算例重新求解工作点，比较原连续调制、理想即时指令、"
        "低频一阶滞后和采样指令的完整闭环谱。其他控制状态仍连续；"
        "本接口不模拟完整数字控制或PWM，也不推荐实机安全采样周期。"
    ),
)
def sampled_command_analysis(request: SampledCommandRequest) -> dict:
    """Recompute from model inputs, never from frozen experimental result tables."""
    from backend.core.average_dq_sampled_command import (
        compare_average_dq_sampled_command,
    )

    if request.preset_id is not None:
        topology, parameters = build_average_dq_verification_case()
        source_kind = "team-defined-average-dq-verification-preset"
    else:
        assert request.topology is not None and request.parameters is not None
        topology = request.topology.model_copy(deep=True)
        parameters = request.parameters.model_copy(deep=True)
        source_kind = "user-supplied-average-dq-case"
    try:
        model = build_average_dq_model(topology, parameters, relative_step=1e-5)
        secondary = build_average_dq_model(topology, parameters, relative_step=5e-6)
        comparisons = [
            compare_average_dq_sampled_command(
                model,
                period,
                holding_frame=hold,
                delay_steps=delay,
                comparison_model=secondary,
            )
            for period in request.sampling_periods_s
            for hold in request.holding_frames
            for delay in request.delay_steps
        ]
    except (ValueError, ArithmeticError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return {
        "schema_version": "experimental-sampled-command-api/1.0",
        "experimental": True,
        "model_scope": {
            "statement": "团队单机无穷大母线平均值模型的指令采样保持对照；其余控制状态连续。",
            "physical_hardware_validation": False,
            "full_digital_controller": False,
            "pwm_switching_model": False,
            "safe_sampling_period_recommendation": False,
            "theorem_status": "not-evaluated-by-sampled-api",
            "api_period_bounds_statement": "周期与记录数上限仅限制本接口计算规模，不代表物理适用范围或安全设置。",
        },
        "provenance": {
            "source_kind": source_kind,
            "preset_id": request.preset_id,
            "paper_fixture": False,
            "result_table_lookup": False,
        },
        "input_topology": topology.model_dump(mode="json"),
        "input_parameters": parameters.model_dump(mode="json"),
        "requested_assumptions": {
            "sampling_periods_s": request.sampling_periods_s,
            "holding_frames": request.holding_frames,
            "delay_steps": request.delay_steps,
        },
        "operating_point": {
            "state": model.operating_point.state.tolist(),
            "closed_rhs_residual_inf": model.operating_point.closed_rhs_residual_inf,
            "active_power_balance_residual_pu": model.operating_point.active_power_balance_residual_pu,
        },
        "comparison_count": len(comparisons),
        "comparisons": comparisons,
    }
