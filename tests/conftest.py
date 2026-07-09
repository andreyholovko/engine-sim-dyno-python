"""Shared fixtures for the engine_sim test suite.

`_build_ecu`/`_build_loop` used to be copy-pasted (structurally identical,
differing only in which EngineSpec/TurboSpec pair) across test_components.py
and each of the three validation test files -- factored here once so a
change to how an ECU/SimulationLoop gets built (e.g. a new required
constructor arg) only needs updating in one place.
"""

import pytest

from engine_sim import ECU, DynoBrake, ParametricEngine, SimulationLoop, Turbo
from engine_sim.presets import (
    B58_340I,
    EA888_GEN3_IS20,
    LS2_NA,
    TURBO_B58,
    TURBO_IS20,
    TURBO_NONE,
)


def _build_ecu(engine_spec, turbo_spec) -> ECU:
    return ECU(
        ParametricEngine(engine_spec),
        Turbo(turbo_spec, firing_order_length=len(engine_spec.firing_order_resolved)),
    )


def _build_loop(engine_spec, turbo_spec) -> SimulationLoop:
    return SimulationLoop(_build_ecu(engine_spec, turbo_spec), DynoBrake())


@pytest.fixture
def ecu() -> ECU:
    """Default EA888/IS20 ECU -- what every component-level test not
    specifically about a different preset should build against."""
    return _build_ecu(EA888_GEN3_IS20, TURBO_IS20)


@pytest.fixture
def ea888_loop() -> SimulationLoop:
    return _build_loop(EA888_GEN3_IS20, TURBO_IS20)


@pytest.fixture
def b58_loop() -> SimulationLoop:
    return _build_loop(B58_340I, TURBO_B58)


@pytest.fixture
def ls2_loop() -> SimulationLoop:
    return _build_loop(LS2_NA, TURBO_NONE)
