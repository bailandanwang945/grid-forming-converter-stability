"""Scientific readiness gate for a Sienna Test 08 cross-model comparison.

The gate deliberately separates two questions:

1. Can the fixed upstream Test 08 baseline be executed or transcribed?
2. Are the original Test 08 and team full models sufficiently aligned for a
   root-by-root eigenvalue comparison?

The first question can be answered positively while the second remains
negative.  Keeping them separate prevents runtime availability from being
misreported as model validation.
"""

from __future__ import annotations


def assess_sienna_test08_run_readiness(
    *,
    source_transcription_verified: bool,
    common_lcl_equations_isomorphic: bool,
    pi_states_isomorphic_after_scaling: bool,
    complete_inner_controls_isomorphic: bool,
    original_power_measurement_ports_identical: bool,
    loaded_full_model_operating_points_aligned: bool,
    external_network_equations_isomorphic: bool,
    full_state_dimensions_equal: bool,
    source_state_count: int,
    team_state_count: int,
) -> dict[str, object]:
    """Return an evidence-bounded M3.4 entry decision."""

    prerequisites = {
        "source_transcription_verified": source_transcription_verified,
        "common_lcl_equations_isomorphic": common_lcl_equations_isomorphic,
        "pi_states_isomorphic_after_scaling": (
            pi_states_isomorphic_after_scaling
        ),
        "complete_inner_controls_isomorphic": (
            complete_inner_controls_isomorphic
        ),
        "original_power_measurement_ports_identical": (
            original_power_measurement_ports_identical
        ),
        "loaded_full_model_operating_points_aligned": (
            loaded_full_model_operating_points_aligned
        ),
        "external_network_equations_isomorphic": (
            external_network_equations_isomorphic
        ),
        "full_state_dimensions_equal": full_state_dimensions_equal,
    }
    blocking_conditions = [
        name for name, passed in prerequisites.items() if not passed
    ]
    cross_model_ready = not blocking_conditions
    return {
        "schema_version": "gfm-sienna-test08-run-readiness/1.0",
        "status": "ready" if cross_model_ready else "not-ready",
        "comparison_target": (
            "original Sienna Test 08 versus original team full model"
        ),
        "state_count_pair": {
            "sienna_test08": source_state_count,
            "team_average_dq": team_state_count,
        },
        "prerequisites": prerequisites,
        "blocking_conditions": blocking_conditions,
        "decisions": {
            "source_only_julia_baseline_may_be_run": (
                source_transcription_verified
            ),
            "root_by_root_cross_model_eigenvalue_comparison_ready": (
                cross_model_ready
            ),
            "julia_runtime_installation_required_by_this_gate": False,
        },
        "scope": {
            "runtime_environment_evaluated": False,
            "julia_executed": False,
            "pscad_executed": False,
            "team_model_validated": False,
            "statement": (
                "A source-only Julia run may confirm the fixed upstream "
                "baseline. It cannot validate the team model until the "
                "remaining original-model equation, operating-point, "
                "network, and state-dimension gates are closed."
            ),
        },
    }
