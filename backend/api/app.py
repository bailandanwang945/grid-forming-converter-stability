from __future__ import annotations

from math import log10

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field


app = FastAPI(title="构网型变流器稳定性分析平台", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class AnalysisRequest(BaseModel):
    scenario_id: str = "author-fig8"
    damping: float = Field(0.5, ge=0.02, le=1.0)
    scr: float = Field(3.0, ge=1.0, le=10.0)


def _analysis_payload(request: AnalysisRequest) -> dict:
    # First frontend contract: calibrated to the controlled Fig. 8 anchors.
    critical_damping = 0.07421769048 * (3.0 / request.scr) ** 0.18
    stable = request.damping > critical_damping
    pole_real_hz = -0.289891361 if stable else 0.0211544371
    pole_imag_hz = 0.399601028 if stable else 0.578113297
    frequencies = [10 ** (-3 + index * 5 / 79) for index in range(80)]
    margins = []
    coverage = []
    for frequency in frequencies:
        modal_dip = 0.34 / (1 + (log10(frequency / 0.58) / 0.34) ** 2)
        damping_lift = 0.78 * (request.damping - critical_damping)
        scr_lift = 0.035 * (request.scr - 3.0)
        margin = damping_lift + scr_lift - modal_dip + 0.08
        margins.append(round(margin, 6))
        coverage.append("covered" if margin > 0 else "uncovered")
    uncovered = sum(value == "uncovered" for value in coverage)
    return {
        "run_id": f"preview-d{request.damping:.3f}-scr{request.scr:.2f}",
        "scenario_id": request.scenario_id,
        "status": "completed",
        "summary": {
            "closed_loop_reference": "stable" if stable else "unstable",
            "criterion_status": (
                "covered-on-grid-under-phase-branch-assumption"
                if uncovered == 0
                else "not-covered-on-grid-under-phase-branch-assumption"
            ),
            "dominant_pole_hz": {
                "real": pole_real_hz,
                "imag": pole_imag_hz,
            },
            "critical_damping_reference": round(critical_damping, 8),
            "uncovered_points": uncovered,
            "frequency_points": len(frequencies),
            "theorem_status": "not-evaluated-by-preview-api",
        },
        "frequency_scan": {
            "frequencies_hz": frequencies,
            "mixed_margin": margins,
            "coverage": coverage,
        },
        "provenance": {
            "mode": "controlled-author-fixture-preview",
            "paper_case": "Cifelli–Anta Fig. 8",
            "interpretation": "判据未覆盖不等于闭环必然失稳。",
        },
    }


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "service": "gfm-stability-api", "version": "0.1.0"}


@app.get("/api/scenarios")
def scenarios() -> dict:
    return {
        "scenarios": [
            {
                "id": "author-fig8",
                "name": "论文 Fig. 8 单机无穷大系统",
                "description": "受控作者算例，用于阻尼变化前后对照。",
                "defaults": {"damping": 0.5, "scr": 3.0},
            }
        ]
    }


@app.post("/api/analysis/run")
def run_analysis(request: AnalysisRequest) -> dict:
    return _analysis_payload(request)
