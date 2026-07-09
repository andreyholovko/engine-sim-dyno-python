"""Turbocharger model: spool lag + wastegate-controlled boost target.

Simplified to what actually matters for a real-time dyno: boost pressure
chases a target (set by RPM/exhaust energy and ECU wastegate duty) with a
first-order lag, which is what produces turbo lag and the "hits boost" feel.
On top of that, charge-air temperature chases its own (slower) target driven
by sustained boost, and the spool response itself is shaped by how the
engine's actual firing order feeds the turbine (see `_pulse_quality`).
"""

from dataclasses import dataclass
from math import exp

from engine_sim.specs import TurboSpec
from engine_sim.units import BAR_TO_PA, T_INTAKE_DEFAULT


@dataclass
class TurboState:
    boost_pa: float = 0.0  # current gauge boost pressure
    intake_air_temp_k: float = T_INTAKE_DEFAULT  # charge temp, ambient + heat soak


@dataclass
class TurboReading:
    """One tick's worth of turbo sensor/diagnostic data -- what a boost gauge
    and the ECU's boost-control logic would actually have available. Mirrors
    EngineReading: the rich, structured result of a tick, not a bare number."""

    boost_pa: float
    target_boost_pa: float  # what the turbo is chasing this tick (spool target)
    wastegate_duty: float  # ECU's commanded wastegate authority this tick, 0-1
    spool_fraction: float  # current boost as a fraction of max_boost_bar, 0-1
    intake_air_temp_k: float  # charge temp actually fed to the engine this tick

    @property
    def boost_bar(self) -> float:
        return self.boost_pa / BAR_TO_PA

    @property
    def target_boost_bar(self) -> float:
        return self.target_boost_pa / BAR_TO_PA


class Turbo:
    # Reference pulse spacing this turbo's hand-tuned spool_width_rpm/
    # spool_time_constant_s already assume: a single-scroll inline-4 (720deg
    # / 4 cylinders = 180deg between pulses sharing one turbine feed). An
    # engine at this baseline gets pulse_quality == 1.0 -- no change to any
    # existing preset's tuned behavior (EA888/IS20 stays exactly as
    # validated). Anything with wider spacing (fewer cylinders per scroll,
    # e.g. a twin-scroll I6) spools smoother/quicker; anything narrower
    # (more cylinders crammed into one shared path) spools peakier/slower.
    _REFERENCE_PULSE_SPACING_DEG = 180.0

    def __init__(self, spec: TurboSpec, firing_order_length: int = 4):
        self.spec = spec
        self.state = TurboState()
        self._pulse_quality = self._compute_pulse_quality(firing_order_length)

    def _compute_pulse_quality(self, firing_order_length: int) -> float:
        """Derived from the engine's *actual* firing order (its pulse
        count), not a decorative parallel constant -- see
        EngineSpec.firing_order_resolved, the same ground truth
        dyno_audio.gd consumes for per-cylinder timing. More crank-degrees
        between pulses sharing one turbine path means less pulse
        interference/reversion between cylinders, so a real twin-scroll I6
        (720/3=240deg per path) spools more smoothly/quickly than a
        single-scroll I4 (720/4=180deg) for the same hand-tuned midpoint --
        this factor narrows/quickens (or widens/slows) that tuned curve
        rather than replacing it, so it stays a modifier, not a rewrite."""
        groups = max(self.spec.exhaust_scroll_groups, 1)
        pulses_per_group = max(firing_order_length, 1) / groups
        pulse_spacing_deg = 720.0 / pulses_per_group
        return max(0.7, min(1.4, pulse_spacing_deg / self._REFERENCE_PULSE_SPACING_DEG))

    def reset(self) -> None:
        # Boost gauge reads zero instantly on lift-off, but charge/intercooler
        # heat doesn't -- intake_air_temp_k deliberately isn't reset here, so
        # a second pull run right after the first still starts hotter than a
        # cold first pull (see TurboSpec.charge_temp_rise_k_per_bar docs).
        self.state.boost_pa = 0.0

    def _target_boost_pa(self, rpm: float, throttle: float, wastegate_duty: float) -> float:
        spec = self.spec
        # Logistic spool curve centered on spool_midpoint_rpm; scaled by
        # throttle as a proxy for exhaust energy (no throttle -> no exhaust
        # flow -> no spool) and by wastegate duty (ECU's boost target cap).
        # spool_width_rpm is narrowed/widened by this engine's actual firing
        # pulse character (see _compute_pulse_quality).
        effective_width = max(spec.spool_width_rpm / self._pulse_quality, 1.0)
        x = (rpm - spec.spool_midpoint_rpm) / effective_width
        spool_fraction = 1.0 / (1.0 + exp(-x))
        return spec.max_boost_bar * BAR_TO_PA * spool_fraction * throttle * wastegate_duty

    def tick(
        self, dt: float, rpm: float, throttle: float, wastegate_duty: float,
        ambient_temp_k: float = T_INTAKE_DEFAULT,
    ) -> TurboReading:
        target = self._target_boost_pa(rpm, throttle, wastegate_duty)
        tau = max(self.spec.spool_time_constant_s / self._pulse_quality, 1e-3)
        alpha = 1.0 - exp(-dt / tau)
        self.state.boost_pa += (target - self.state.boost_pa) * alpha
        self.state.boost_pa = max(0.0, self.state.boost_pa)

        max_boost_pa = self.spec.max_boost_bar * BAR_TO_PA
        spool_fraction = self.state.boost_pa / max_boost_pa if max_boost_pa > 0 else 0.0

        # Charge-air heat soak: chases ambient + a rise proportional to
        # *current* boost, on its own (much slower) thermal lag -- boost_pa
        # already reflects this tick's spool, so heating tracks the actual
        # compressor work being done, not the eventual target.
        target_iat_k = ambient_temp_k + self.spec.charge_temp_rise_k_per_bar * (self.state.boost_pa / BAR_TO_PA)
        heat_tau = max(self.spec.heat_soak_time_constant_s, 1e-3)
        heat_alpha = 1.0 - exp(-dt / heat_tau)
        self.state.intake_air_temp_k += (target_iat_k - self.state.intake_air_temp_k) * heat_alpha

        return TurboReading(
            boost_pa=self.state.boost_pa,
            target_boost_pa=target,
            wastegate_duty=wastegate_duty,
            spool_fraction=max(0.0, min(1.0, spool_fraction)),
            intake_air_temp_k=self.state.intake_air_temp_k,
        )

    @property
    def boost_bar(self) -> float:
        return self.state.boost_pa / BAR_TO_PA
