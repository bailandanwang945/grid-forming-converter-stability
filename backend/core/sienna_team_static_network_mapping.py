"""Equation gate for the common static two-bus network layer."""

from __future__ import annotations

import numpy as np
from numpy.typing import ArrayLike, NDArray


SYSTEM_BASE_POWER_MVA = 100.0
DEVICE_BASE_POWER_MVA = 2.75
SOURCE_NETWORK_RESISTANCE_PU_SYSTEM = 0.0
SOURCE_NETWORK_REACTANCE_PU_SYSTEM = 0.075
INFINITE_BUS_VOLTAGE = complex(
    1.0000099992980975,
    6.874931250857116e-8,
)


def _finite_current(value: ArrayLike) -> NDArray[np.float64]:
    current = np.asarray(value, dtype=np.float64)
    if current.shape != (2,) or not np.all(np.isfinite(current)):
        raise ValueError("network current must be a finite two-vector")
    return current


def source_static_terminal_voltage(
    converter_to_network_current_device_pu: ArrayLike,
) -> complex:
    """Apply the Test 08 two-bus algebraic network equation."""

    current = _finite_current(converter_to_network_current_device_pu)
    current_complex = complex(float(current[0]), float(current[1]))
    base_ratio = DEVICE_BASE_POWER_MVA / SYSTEM_BASE_POWER_MVA
    impedance_system = complex(
        SOURCE_NETWORK_RESISTANCE_PU_SYSTEM,
        SOURCE_NETWORK_REACTANCE_PU_SYSTEM,
    )
    return INFINITE_BUS_VOLTAGE + impedance_system * base_ratio * current_complex


def team_static_terminal_voltage(
    network_to_converter_current_device_pu: ArrayLike,
) -> complex:
    """Apply the team static-line equation with its declared current sign."""

    current = _finite_current(network_to_converter_current_device_pu)
    current_complex = complex(float(current[0]), float(current[1]))
    base_ratio = DEVICE_BASE_POWER_MVA / SYSTEM_BASE_POWER_MVA
    impedance_device = base_ratio * complex(
        SOURCE_NETWORK_RESISTANCE_PU_SYSTEM,
        SOURCE_NETWORK_REACTANCE_PU_SYSTEM,
    )
    return INFINITE_BUS_VOLTAGE - impedance_device * current_complex


def run_static_network_mapping_audit() -> dict[str, object]:
    """Verify base conversion and current-direction mapping independently."""

    probes = (
        np.array([0.0, 0.0]),
        np.array([0.4, -0.2]),
        np.array([-0.7, 0.35]),
    )
    rows: list[dict[str, object]] = []
    maximum_difference = 0.0
    for source_current in probes:
        team_current = -source_current
        source_voltage = source_static_terminal_voltage(source_current)
        team_voltage = team_static_terminal_voltage(team_current)
        difference = abs(source_voltage - team_voltage)
        maximum_difference = max(maximum_difference, difference)
        rows.append(
            {
                "source_current_converter_to_network_pu": source_current.tolist(),
                "team_current_network_to_converter_pu": team_current.tolist(),
                "source_terminal_voltage": [
                    float(source_voltage.real),
                    float(source_voltage.imag),
                ],
                "team_terminal_voltage": [
                    float(team_voltage.real),
                    float(team_voltage.imag),
                ],
                "voltage_difference_abs_pu": float(difference),
            }
        )

    probe = probes[1]
    correct = source_static_terminal_voltage(probe)
    impedance_without_base_conversion = complex(
        SOURCE_NETWORK_RESISTANCE_PU_SYSTEM,
        SOURCE_NETWORK_REACTANCE_PU_SYSTEM,
    )
    wrong_base = INFINITE_BUS_VOLTAGE + impedance_without_base_conversion * complex(
        float(probe[0]), float(probe[1])
    )
    wrong_sign = team_static_terminal_voltage(probe)
    wrong_base_difference = float(abs(correct - wrong_base))
    wrong_sign_difference = float(abs(correct - wrong_sign))
    equation_gate = 1.0e-12
    counterexample_gate = 1.0e-3
    passed = bool(
        maximum_difference <= equation_gate
        and wrong_base_difference >= counterexample_gate
        and wrong_sign_difference >= counterexample_gate
    )
    converted_impedance = (
        SOURCE_NETWORK_REACTANCE_PU_SYSTEM
        * DEVICE_BASE_POWER_MVA
        / SYSTEM_BASE_POWER_MVA
    )
    return {
        "schema_version": "gfm-sienna-team-static-network-mapping/1.0",
        "status": "passed" if passed else "failed",
        "model_contract": {
            "network_state_count": 0,
            "source_current_direction": "converter-to-network",
            "team_current_direction": "network-to-converter",
            "system_base_power_mva": SYSTEM_BASE_POWER_MVA,
            "device_base_power_mva": DEVICE_BASE_POWER_MVA,
            "source_reactance_pu_system_base": (
                SOURCE_NETWORK_REACTANCE_PU_SYSTEM
            ),
            "converted_reactance_pu_device_base": converted_impedance,
            "infinite_bus_voltage": [
                float(INFINITE_BUS_VOLTAGE.real),
                float(INFINITE_BUS_VOLTAGE.imag),
            ],
        },
        "verification_gates": {
            "maximum_voltage_difference_abs_pu": equation_gate,
            "minimum_counterexample_difference_abs_pu": counterexample_gate,
        },
        "maximum_voltage_difference_abs_pu": float(maximum_difference),
        "counterexamples": {
            "base_conversion_omitted_difference_abs_pu": wrong_base_difference,
            "current_direction_inversion_omitted_difference_abs_pu": (
                wrong_sign_difference
            ),
        },
        "probes": rows,
        "scope": {
            "common_static_network_equations_isomorphic": passed,
            "original_team_dynamic_line_isomorphic_to_source_network": False,
            "full_model_eigenvalues_comparable_from_this_gate": False,
            "statement": (
                "The gate proves only the algebraic two-bus voltage-current "
                "map after device-base conversion and current-sign inversion. "
                "The team's original dynamic RL line remains a different "
                "network realization."
            ),
        },
    }
