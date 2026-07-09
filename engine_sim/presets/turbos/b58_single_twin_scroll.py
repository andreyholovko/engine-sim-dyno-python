"""MHI single twin-scroll turbo, paired with B58_340I.

A twin-scroll housing (two separate exhaust-gas paths feeding one turbine,
one per exhaust bank of three cylinders) spools noticeably faster than a
comparable single-scroll turbo -- consistent with the B58's torque plateau
starting at just 1380rpm, barely above idle."""

from engine_sim import TurboSpec

TURBO_B58 = TurboSpec(
    name="MHI single twin-scroll (B58)",
    max_boost_bar=1.2,
    spool_midpoint_rpm=800.0,
    spool_width_rpm=200.0,
    spool_time_constant_s=0.12,
    # Twin-scroll: cylinders 1-5-3 feed one turbine path, 6-2-4 the other --
    # each path only ever sees every-other firing event, spaced evenly
    # (720/3=240deg) instead of all six sharing one manifold at 120deg. See
    # Turbo._compute_pulse_quality(): this is what actually derives "spools
    # noticeably faster" from the real firing order instead of it being
    # nothing but a hand-tuned spool_width_rpm/spool_time_constant_s.
    exhaust_scroll_groups=2,
)
