"""Bounded frequency-response audit for modulation-delay realizations.

The Padé coefficient recurrence is adapted from ``python-control`` 0.10.2
(``control.delay.pade``), BSD-3-Clause, fixed source commit
17d8b0ddc290b592a69a664a1b33c8973a0a9da7.  The project retains the license
text in its research-source notices.  Only the square [n/n] case required by
this audit is exposed here.
"""

from __future__ import annotations

from cmath import exp
from math import isfinite, pi

import numpy as np

from backend.core.sienna_team_common_modulation_delay import (
    TEAM_DECLARED_MODULATION_TIME_CONSTANT_S,
    run_common_modulation_delay_audit,
)


PADE_ORDERS = (1, 2, 3)
AUDIT_FREQUENCY_LIMIT_HZ = 200.0
AUDIT_FREQUENCY_POINT_COUNT = 2001


class DelayApproximationError(ValueError):
    """Raised when a delay-approximation request is outside the contract."""


def pade_delay_coefficients(
    delay_s: float, order: int
) -> tuple[list[float], list[float]]:
    """Return descending-power coefficients of the square [n/n] Padé model."""

    delay = float(delay_s)
    if not isfinite(delay) or delay < 0.0:
        raise DelayApproximationError("delay must be finite and non-negative")
    if isinstance(order, bool) or not isinstance(order, int) or order < 0:
        raise DelayApproximationError("Padé order must be a non-negative integer")
    if delay == 0.0 or order == 0:
        return [1.0], [1.0]

    numerator = [0.0] * (order + 1)
    numerator[-1] = 1.0
    coefficient = 1.0
    for index in range(1, order + 1):
        coefficient *= (
            -delay
            * (order - index + 1)
            / (2 * order - index + 1)
            / index
        )
        numerator[order - index] = coefficient

    denominator = [0.0] * (order + 1)
    denominator[-1] = 1.0
    coefficient = 1.0
    for index in range(1, order + 1):
        coefficient *= (
            delay
            * (order - index + 1)
            / (2 * order - index + 1)
            / index
        )
        denominator[order - index] = coefficient

    leading = denominator[0]
    return (
        [value / leading for value in numerator],
        [value / leading for value in denominator],
    )


def _evaluate_polynomial(coefficients: list[float], value: complex) -> complex:
    result = 0.0j
    for coefficient in coefficients:
        result = result * value + coefficient
    return result


def _phase_error_rad(approximation: complex, reference: complex) -> float:
    return float(np.angle(approximation / reference))


def _response_payload(response: complex, exact: complex) -> dict[str, float]:
    return {
        "magnitude": float(abs(response)),
        "phase_deg": float(np.angle(response) * 180.0 / pi),
        "magnitude_error": float(abs(response) - 1.0),
        "phase_error_deg_against_exact": float(
            _phase_error_rad(response, exact) * 180.0 / pi
        ),
    }


def run_delay_approximation_audit() -> dict[str, object]:
    """Compare exact delay, local-dq lag, and Padé orders on a fixed band."""

    delay = TEAM_DECLARED_MODULATION_TIME_CONSTANT_S
    modulation_audit = run_common_modulation_delay_audit()
    declared_point = next(
        point
        for point in modulation_audit["points"]
        if point["modulation_time_constant_s"] == delay
    )
    named_frequencies = {
        "low_frequency_mode": declared_point["low_frequency_mode"]["pole"][
            "frequency_hz"
        ],
        "wide_frequency_mode": declared_point["wide_frequency_mode"]["pole"][
            "frequency_hz"
        ],
    }
    coefficients = {
        order: pade_delay_coefficients(delay, order) for order in PADE_ORDERS
    }

    named_points: dict[str, object] = {}
    for name, frequency_hz in named_frequencies.items():
        angular_frequency = 2.0 * pi * frequency_hz
        argument = 1j * angular_frequency
        exact = exp(-argument * delay)
        local_lag = 1.0 / (1.0 + argument * delay)
        pade_payload = {}
        for order, (numerator, denominator) in coefficients.items():
            response = _evaluate_polynomial(
                numerator, argument
            ) / _evaluate_polynomial(denominator, argument)
            pade_payload[str(order)] = _response_payload(response, exact)
        named_points[name] = {
            "frequency_hz": frequency_hz,
            "dimensionless_omega_delay": angular_frequency * delay,
            "exact_transport_delay": _response_payload(exact, exact),
            "local_dq_first_order_lag": _response_payload(local_lag, exact),
            "pade": pade_payload,
        }

    frequencies = np.linspace(
        0.0, AUDIT_FREQUENCY_LIMIT_HZ, AUDIT_FREQUENCY_POINT_COUNT
    )
    maximum_phase_error_by_order: dict[str, float] = {}
    maximum_magnitude_error_by_order: dict[str, float] = {}
    all_poles_left_half_plane = True
    for order, (numerator, denominator) in coefficients.items():
        phase_errors = []
        magnitude_errors = []
        for frequency_hz in frequencies:
            argument = 1j * 2.0 * pi * frequency_hz
            exact = exp(-argument * delay)
            response = _evaluate_polynomial(
                numerator, argument
            ) / _evaluate_polynomial(denominator, argument)
            phase_errors.append(abs(_phase_error_rad(response, exact)))
            magnitude_errors.append(abs(abs(response) - 1.0))
        maximum_phase_error_by_order[str(order)] = float(
            max(phase_errors) * 180.0 / pi
        )
        maximum_magnitude_error_by_order[str(order)] = float(
            max(magnitude_errors)
        )
        all_poles_left_half_plane = all_poles_left_half_plane and bool(
            np.all(np.roots(denominator).real < 0.0)
        )

    order_sensitivity_resolved = (
        maximum_phase_error_by_order["3"]
        < maximum_phase_error_by_order["2"]
        < maximum_phase_error_by_order["1"]
    )
    passed = (
        all_poles_left_half_plane
        and order_sensitivity_resolved
        and max(maximum_magnitude_error_by_order.values()) < 1.0e-10
    )
    return {
        "schema_version": "gfm-delay-approximation-audit/1.0",
        "status": "passed" if passed else "failed",
        "model_contract": {
            "delay_s": delay,
            "pade_orders": list(PADE_ORDERS),
            "audit_frequency_range_hz": [0.0, AUDIT_FREQUENCY_LIMIT_HZ],
            "audit_frequency_point_count": AUDIT_FREQUENCY_POINT_COUNT,
            "named_frequencies_source": (
                "M3.3c1 local-dq first-order modulation scan at T_mod=1 ms"
            ),
        },
        "pade_coefficients_descending_s": {
            str(order): {
                "numerator": numerator,
                "denominator": denominator,
            }
            for order, (numerator, denominator) in coefficients.items()
        },
        "named_frequency_comparison": named_points,
        "band_summary": {
            "maximum_phase_error_deg_against_exact_by_order": (
                maximum_phase_error_by_order
            ),
            "maximum_magnitude_error_by_order": (
                maximum_magnitude_error_by_order
            ),
            "all_pade_poles_left_half_plane": all_poles_left_half_plane,
            "phase_error_decreases_through_order_three": (
                order_sensitivity_resolved
            ),
        },
        "scope": {
            "frequency_response_only": True,
            "closed_loop_poles_with_exact_delay_compared": False,
            "pade_poles_reported_as_physical_modes": False,
            "switching_waveforms_compared": False,
            "statement": (
                "This audit verifies delay-realization frequency responses; "
                "it does not turn an infinite-dimensional transport delay into "
                "a claimed physical finite-state mode set."
            ),
        },
        "provenance": {
            "algorithm": "python-control control.delay.pade, adapted square case",
            "version": "0.10.2",
            "commit": "17d8b0ddc290b592a69a664a1b33c8973a0a9da7",
            "license": "BSD-3-Clause",
        },
    }
