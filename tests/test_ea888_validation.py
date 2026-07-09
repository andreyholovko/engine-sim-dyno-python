"""Validates the parametric engine model against VW's own published figures
for the EA888 Gen3 (MK7 GTI, IS20): 147kW/200PS, 320Nm torque plateau from
1500-4400rpm, peak power between 4400-6000rpm, IS20 full boost by ~3200rpm.

This is a mean-value model, not a CFD-grade replica -- tolerances are
deliberately loose (test comments explain why each one is sized as it is).

Uses the `ea888_loop` fixture (tests/conftest.py) -- a fresh SimulationLoop
built for this preset, same as every other test here would build by hand.
"""

from engine_sim.presets import TURBO_IS20


def test_power_pull_produces_a_full_curve(ea888_loop):
    readings = ea888_loop.run_power_pull()
    assert len(readings) > 10
    # Sweep terminates at the ECU's rev-limiter threshold (just under
    # redline), not the hard cutoff itself -- that's the last usable reading.
    assert readings[-1].rpm >= ea888_loop.ecu.rev_limiter_threshold_rpm


def test_power_pull_safety_cap_terminates_a_pull_that_never_reaches_redline(ea888_loop):
    """Branch-coverage gap found by inspection: run_power_pull()'s 60s
    safety cap (max_ticks) had never actually been exercised -- every other
    test reaches the rev limiter well before that. Force it with an
    absurdly slow ramp rate and confirm it terminates at exactly max_ticks
    readings instead of running away."""
    dt = 0.01
    readings = ea888_loop.run_power_pull(dt=dt, ramp_rate_rpm_s=1.0)
    assert len(readings) == int(60.0 / dt)
    assert readings[-1].rpm < ea888_loop.ecu.rev_limiter_threshold_rpm


def test_peak_torque_matches_published_plateau(ea888_loop):
    readings = ea888_loop.run_power_pull()
    peak = max(readings, key=lambda r: r.engine.net_torque_nm)
    # Published plateau is 320 Nm; +-15% covers MVEM approximation error
    # while still catching a materially wrong combustion model.
    assert 272.0 <= peak.engine.net_torque_nm <= 368.0, peak.engine.net_torque_nm
    # Plateau is spec'd 1500-4400rpm; allow some slack either side.
    assert 1200.0 <= peak.rpm <= 4800.0, peak.rpm


def test_torque_plateau_is_flat_across_published_band(ea888_loop):
    readings = ea888_loop.run_power_pull()
    in_band = [r for r in readings if 1600.0 <= r.rpm <= 4300.0]
    assert len(in_band) > 5
    torques = [r.engine.net_torque_nm for r in in_band]
    # "Flat" plateau: shouldn't sag more than ~20% peak-to-trough inside the
    # band VW itself calls constant.
    assert (max(torques) - min(torques)) / max(torques) < 0.20


def test_peak_power_matches_published_figure(ea888_loop):
    readings = ea888_loop.run_power_pull()
    peak = max(readings, key=lambda r: r.power_w)
    # Published peak is 147kW; +-15% tolerance for the same reason as torque.
    assert 125.0 <= peak.power_kw <= 169.0, peak.power_kw
    assert 4000.0 <= peak.rpm <= 6300.0, peak.rpm


def test_power_pull_resets_residual_boost_from_prior_use(ea888_loop):
    """A power pull run right after free-play throttle use must start cold
    (unspooled), the way a real pull starts from idle -- not carry over
    whatever boost was built up a moment ago."""
    for _ in range(200):
        ea888_loop.tick(0.02, throttle=1.0, mode="free_accel")
    assert ea888_loop.ecu.turbo.boost_bar > 0.1  # sanity: it really did spool up

    readings = ea888_loop.run_power_pull()
    assert readings[0].boost_bar < 0.05


def test_turbo_spools_by_published_rpm(ea888_loop):
    readings = ea888_loop.run_power_pull()
    at_3200 = min(readings, key=lambda r: abs(r.rpm - 3200.0))
    # "Full boost by ~3200rpm" -- expect it to be at least ~90% spooled by then.
    assert at_3200.boost_bar >= 0.9 * TURBO_IS20.max_boost_bar


def test_energy_conservation_free_accel_matches_inertia_method(ea888_loop):
    """Cross-check: for free_accel mode, the torque implied by measured
    angular acceleration (I*alpha, the way a real inertia dyno derives torque)
    should match the net torque the sim computed directly -- if it doesn't,
    the integrator has a bug, not the combustion model."""
    dt = 0.005
    ea888_loop.rpm = 3000.0
    r1 = ea888_loop.tick(dt, throttle=1.0, mode="free_accel")
    rpm_before = 3000.0
    from engine_sim.units import rpm_to_rad_s

    alpha = (rpm_to_rad_s(r1.rpm) - rpm_to_rad_s(rpm_before)) / dt
    total_inertia = ea888_loop.ecu.engine.spec.crank_inertia_kgm2 + ea888_loop.brake.dyno_inertia_kgm2
    implied_net_torque = alpha * total_inertia
    expected_net_torque = r1.engine.net_torque_nm - r1.brake_torque_nm
    assert abs(implied_net_torque - expected_net_torque) < 1e-6
