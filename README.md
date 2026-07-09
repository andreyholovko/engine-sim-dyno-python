# Drag Racing Dyno Simulator

A real-time, parametric engine/turbo/ECU simulation, driven from Godot via an
embedded Python runtime (py4godot). This repo is an **engine dyno** —
crank-only, no transmission, no wheels, no tire-road friction. There's no
drag-strip/transmission phase currently planned; work right now is focused on
optimizing and deepening the realism of the dyno itself (more validated
engines, tighter physical modeling, better procedural audio), not on adding
new phases or features.

## Layout

```
engine_sim/                    Pure Python simulation core (zero Godot imports)
  specs.py                     EngineSpec / TurboSpec / CamSpec -- data-driven params,
                                shared by core/ and presets/, kept at top level since
                                both depend on it
  session.py                   DynoSession -- the one interface every frontend drives
                                (construction, live-override controls, and a flattened
                                DynoSnapshot for display), so the CLI, Godot, and any
                                future consumer can never silently diverge
  core/                        The simulation itself
    engine.py                  Engine (abstract) + ParametricEngine (mean-value engine model)
    turbo.py                   Turbo: spool lag + wastegate-controlled boost target
    ecu.py                     ECU: fuel control (AFR), wastegate duty, rev limiter, MAP
    dyno.py                    DynoBrake (load model) + SimulationLoop (tick loop)
  presets/                     Real-world engine/turbo data, one file each
    engines/
      ea888_gen3_is20.py       EA888_GEN3_IS20 -- the validation target, actually wired in
      ea888_gen3b_is38.py      EA888_GEN3B_IS38 -- Miller-cycle example, decorative only
    turbos/
      is20.py                 TURBO_IS20 -- actually wired in; edit max_boost_bar here
      is38.py                 TURBO_IS38 -- decorative only
tests/                         pytest suite, incl. validation against published EA888 figures
godot/                         Godot 4.7+ project
  addons/py4godot/             Embedded-Python GDExtension (gitignored -- see setup below)
  scripts/
    dyno_controller.py         py4godot Node: owns a DynoSession, ticks it every frame
    dyno_ui.gd                 Wires sliders/buttons/labels to the controller
    dyno_graph.gd              Live torque/power-vs-rpm plot, auto-scaling axes per engine
    dyno_audio.gd              Procedural engine + turbo sound, synthesized live from DynoController
  scenes/Dyno.tscn             The dyno interface (DynoController + DynoAudio + UI)
```

Everything under `engine_sim/` is still reached the same way from outside the
package (`from engine_sim import ECU, ...`, `from engine_sim.presets import
EA888_GEN3_IS20, TURBO_IS20`) -- `core/` and `presets/` are an internal
reorganization, not a public API change. Adding a new engine or turbo is just
a new file under `presets/engines/` or `presets/turbos/`, plus one line in
that folder's `__init__.py`.

## Why it's built this way

The simulation core (`engine_sim/`) is plain Python with no Godot imports at
all -- it's a mean-value engine model (MVEM), the same technique used in
real hardware-in-the-loop ECU test rigs: given throttle/RPM/manifold pressure
it computes air mass flow, fuel flow, and net crank torque from actual engine
parameters (displacement, cylinders, compression ratio, cam profile), not a
canned curve. `dyno_controller.py` is the *only* file where Godot and
engine_sim touch, wrapping a `DynoSession` as a py4godot Node. If the
py4godot binding ever becomes a dead end, only that adapter needs replacing.

**`DynoSession` (`engine_sim/session.py`) is the one interface every
consumer drives** -- `dyno_cli.py` and `dyno_controller.py` each used to
hand-build their own `Engine`/`Turbo`/`ECU`/`SimulationLoop` and hand-flatten
readings for display; both copies happened to agree, but nothing enforced
that. Now both just do `DynoSession()`, call `set_afr_override()` /
`set_boost_target_percent()` / `start_power_pull()` / `tick()`, and read a
`DynoSnapshot` back. `tests/test_session.py` locks this in with a test that
builds two independent sessions and asserts they produce bit-identical
curves -- any future consumer should do the same `DynoSession()` construction
rather than reaching into `engine_sim.core` directly.

## Running the Python simulation (fully verified, no Godot needed)

```bash
.venv/bin/pip install -e ".[dev]"
.venv/bin/python -m pytest -q
```

88 tests pass (add `--cov=engine_sim --cov=dyno_cli --cov-report=term-missing`
for a coverage breakdown -- currently 99%, and the remaining lines are the
abstract `Engine.compute` stub, one unused convenience property, and the
`if __name__ == "__main__"` guard), including validation against three
independently-published figures:

- **EA888 Gen3 (MK7 GTI, IS20)** -- VW/Audi's own published 147kW/200PS,
  320Nm torque plateau 1500-4400rpm, IS20 full boost by ~3200rpm. Simulated:
  323.8Nm peak torque @ 2636rpm, 156.1kW peak power @ 4928rpm.
- **BMW B58B30 (340i)** -- BMW's published 320hp (238.7kW) @ 5500-6500rpm,
  330lb-ft (447Nm) flat 1380-5000rpm, redline 7000rpm. Simulated: 446.1Nm
  peak torque @ 2052rpm, 235.8kW peak power @ 5352rpm. (Despite being
  colloquially called "twin-turbo," the B58 uses one turbocharger with a
  twin-scroll housing, not two turbos -- modeled as a single `TurboSpec`,
  same as every other preset here.)
- **GM LS2 (Corvette C6)** -- GM's published 400hp (298.3kW) @ 6000rpm,
  400lb-ft (542.4Nm) @ 4400rpm, redline 6500rpm. Simulated: 539.0Nm peak
  torque @ 4206rpm, 309.6kW peak power @ 5670rpm. The first naturally-
  aspirated preset (paired with `TURBO_NONE`, `max_boost_bar=0.0` -- no
  special-casing anywhere, boost just never builds) -- and the first one
  that needed `EngineSpec.ve_rise_rpm`: turbocharged engines get their
  low-end torque rise from boost building, but with no boost to lean on, the
  LS2's volumetric-efficiency curve itself has to rise from idle to its
  4400rpm peak. Defaults to a no-op (0.0) for every other preset, verified
  by `tests/test_components.py::test_ve_rise_phase_is_opt_in_only`.

Tolerances are documented in `tests/test_ea888_validation.py` /
`tests/test_b58_validation.py` / `tests/test_ls2_validation.py`, which also
explain *why* each is sized the way it is (this is a simplified physical
model, not a CFD replica). There's also a regression test guarding a real bug
that turned up during manual testing: a power pull run right after free-play
use used to carry over residual turbo boost instead of starting cold from
idle.

**Selecting an engine:** `ENGINE_CHOICES` in `engine_sim/presets/__init__.py`
is the registry both `DynoSession.select_engine(key)` and every UI read from
-- currently `"ea888_gen3_is20"` (the default), `"b58_340i"`, and `"ls2_na"`,
each always paired with its own *stock* turbo. In the CLI: `engine ls2_na`
(or `engines` to list choices). In Godot: the **Engine** dropdown at the top
of the UI. `EA888_GEN3B_IS38` exists in `presets/` for variety (the
Miller-cycle example) but is deliberately left out of `ENGINE_CHOICES` --
it's explicitly *not* validated against a published dyno sheet (see that
file's docstring), so it's not offered as an equally-trustworthy option.

**Selecting a turbo (independent of engine):** `TURBO_CHOICES_BY_ENGINE` is a
second, separate registry -- real (or clearly-labeled representative) turbo
upgrade paths for each `ENGINE_CHOICES` engine, swappable via
`DynoSession.select_turbo(key)`/`select_turbo_by_index()` *without* changing
the engine. The point is watching one validated engine spec produce a
genuinely different torque/power curve and spool timing under a different
turbo, the same way a real turbo swap does:

- **EA888**: stock IS20 -> **IS38** (the real "IS38 hybrid swap", one of the
  most common EA888 upgrades -- `TURBO_IS38` used to be a decorative preset
  with an unrealistic 3.35 bar placeholder; it's now a real selectable
  option at a realistic ~1.8 bar) -> aftermarket big-frame hybrid
  (TTE-class, representative of that category, ~2.1 bar, spools noticeably
  later).
- **B58**: stock 340i unit -> **B58TU** (the real, bigger factory turbo
  BMW actually fits to the M340i/Supra, ~1.45 bar vs the 340i's 1.2) ->
  aftermarket big single (Pure Stage 2-class, representative, ~2.0 bar --
  and genuinely abandons the twin-scroll housing for a single big turbine,
  a real documented trade at that size, so it also spools later/less
  decisively than either twin-scroll option).
- **LS2**: naturally aspirated (stock) -> a representative twin-turbo kit
  (~0.7 bar/10psi, a conservative stock-internals-safe point -- there's no
  one canonical "the LS2 turbo" the way there's an OEM path for the other
  two, turbocharging an LS is a huge, kit-dependent aftermarket world).

In the CLI: `turbos` to list the current engine's choices, `turbo <key>` to
switch. In Godot: the **Turbo** dropdown next to Engine, repopulated
whenever you change engines (a turbo choice from one engine isn't valid on
another). `TURBO_CHOICES_BY_ENGINE`'s own docstring in `presets/__init__.py`
is explicit about which numbers are real/documented versus representative
of a category -- read it before treating any of these as verified spec
sheets.

## Fastest way to actually drive it: `dyno_cli.py`

No Godot required. An interactive terminal dyno against the exact same
`engine_sim` core:

```bash
.venv/bin/python dyno_cli.py
```

```
dyno> engines            # list selectable engines
dyno> engine b58_340i    # switch engine (and its stock turbo) mid-session
dyno> turbos             # list turbo choices for the CURRENT engine
dyno> turbo b58tu        # swap turbos on the SAME engine -- different curve
dyno> throttle 100
dyno> step 3            # advance 3s at current throttle, free-play mode
dyno> afr 11.5           # override target AFR (or "afr auto" to release it)
dyno> boost 50           # cap wastegate authority at 50% of max boost (or "boost auto")
dyno> octane 85          # set pump octane -- knock/timing-retard model (or "octane auto")
dyno> sweep              # paced WOT power pull, prints the torque/power curve
dyno> quit
```

## Running the Godot dyno UI

Confirmed working in a real Godot 4.7 editor. `godot/addons/` is gitignored
(the py4godot GDExtension is a ~124MB bundled CPython runtime -- not
something to put in git), so **it will not be there after a fresh clone**.
Set it up once per machine:

1. Install **Godot 4.7** (the bundled py4godot build pins
   `compatibility_minimum = 4.7.0`).
2. Download the py4godot release for your platform:
   https://github.com/niklas2902/py4godot/releases/latest (`py4godot.zip`).
   It's a multi-platform bundle (~247MB); on macOS you only need the
   `cpython-3.14.4-darwin64` folder (arm64). Extract and place under
   `godot/addons/py4godot/` so that `godot/addons/py4godot/python.gdextension`
   exists alongside it, e.g.:
   ```
   godot/addons/py4godot/
     python.gdextension
     cpython-3.14.4-darwin64/
     LICENSE, Python.svg, dependencies.txt, get_pip.py,
     install_dependencies.py, signal_script.py
   ```
   (On Linux/Windows use the matching `cpython-3.14.4-<platform>` folder
   instead -- the `.gdextension` file already lists all of them.)
3. Open `godot/project.godot`. Godot should auto-detect the extension; enable
   it if asked.
4. Run the scene (`scenes/Dyno.tscn` is the main scene).

### Gotchas found by actually running it

- Editing the wrong preset is an easy mistake to make: see "Which presets are
  actually live" above -- `TURBO_IS38`/`EA888_GEN3B_IS38` are decorative only.
- py4godot itself is still labelled "early phase, more a demo than for bigger
  projects" by its own maintainer -- if something behaves oddly, that binding
  is the more likely suspect than `engine_sim`, which is fully pytest-covered.

### What each control does

- **Engine dropdown** -- selects from `ENGINE_CHOICES`, rebuilding the
  session's Engine/Turbo/ECU for the chosen preset (`DynoSession.
  select_engine()`). Aborts any in-progress pull. The graph (below) rescales
  its axes automatically for whichever engine is selected.
  **Real bug found and fixed here:** the dropdown initially didn't work at
  all -- `engine_choices`/`engine_name` are `str`-typed py4godot properties,
  and py4godot's own examples only ever show `int`/`float`/`bool`/`Vector3`,
  never `str`. Selection now goes through `select_engine_by_index(int)` end
  to end (`dyno_ui.gd` hardcodes the picker's labels, matching
  `ENGINE_CHOICES`' order, instead of parsing `engine_choices`) -- `int` is a
  type already confirmed working (`rpm`, `engine_count`, etc. all display
  correctly). The `str` properties are left in place as a nice-to-have/debug
  aid, but nothing load-bearing depends on them anymore.
- **Turbo dropdown** -- selects from the current engine's
  `TURBO_CHOICES_BY_ENGINE` list (`DynoSession.select_turbo_by_index()`),
  keeping the same engine but rebuilding Turbo/ECU -- same `str`-across-
  py4godot-boundary reasoning and index-addressed selection as the Engine
  dropdown. Repopulated whenever the Engine dropdown changes (a different
  engine has an entirely different turbo lineup); resets to that engine's
  own stock unit automatically. Aborts any in-progress pull.
- **Target Boost slider (0-100%)** -- caps the ECU's wastegate authority as a
  fraction of the turbo's `max_boost_bar` (`TURBO_IS20`, currently 1.3 bar).
  50% target measurably drops peak torque from ~324Nm to ~230Nm -- verified
  directly against the sim, not just wired up and assumed.
- **Override target AFR** -- checkbox + slider to force a fixed AFR instead
  of the ECU's own load-based control law (stoich cruise -> ~12.5 at WOT).
- **Throttle slider (vertical, 0-100%)** -- live, while running, and it
  actually controls the sweep: during an active pull the brake resists the
  engine hard to hold a controlled pace (up to 400rpm/s at full throttle,
  scaling down with it -- exactly what a real engine dyno's brake does,
  loading the engine rather than letting it free-rev against nothing).
  Back off mid-pull and it stops being paced at all -- the engine decelerates
  under its own engine braking + dyno inertia, exactly like lifting for real
  (see "Off-throttle" below). **Start Power Pull** resets to idle/cold boost
  and starts recording the run (clears the graph, arms the rev-limiter-
  triggered finish) -- you then drive the throttle yourself for the actual
  sweep. At 0% throttle the dyno brake holds `idle_rpm_target`, pull active
  or not.
- **Intake Air Temp (C) readout** -- the charge temperature the engine is
  actually breathing this tick: ambient plus whatever heat soak the turbo
  has built up (see below). Naturally-aspirated (LS2) always reads ambient.

### Sound

`dyno_audio.gd` (a `DynoAudio` node alongside `DynoController` in
`Dyno.tscn`) procedurally synthesizes engine and turbo sound live from the
controller's state -- no audio assets. Two signal chains, each built from
pure functions of a single continuously-advancing phase (never hard-reset,
never driven by a separate envelope that can jump):

- **Engine**: phase is counted in cylinders, not radians, so each firing
  event lands a cubed half-sine pulse timed to real `cylinders * rpm / 120`
  firing frequency. Per-cylinder amplitude (manufacturing-tolerance/runner-
  length character) comes from `EngineSpec.firing_order_resolved`, is fixed
  per engine (deterministic RNG seeded from `engine_generation`, not redrawn
  every firing event), and always changes on a waveform zero-crossing, so
  swapping engines mid-session can never click. A one-pole lowpass
  (`_engine_lp`) darkens the combustion tone itself with displacement (EA888
  2.0L brightest, LS2 6.0L deepest).
  **Then it goes through an exhaust stage** (`_exhaust_filter()`) -- a real
  gap found by ear: the raw per-cylinder pulses alone sounded like
  individually-audible clicks rather than one continuous note, because a
  single one-pole filter softens each pulse's edges without actually
  blending consecutive ones together. A 2-pole resonant (state-variable)
  lowpass, cutoff calibrated against real firing frequencies (not just
  "lower than the engine filter's") -- below cutoff (idle/low rpm) pulses
  stay a bit distinct (a real idle IS somewhat lopey, not a pure hum); once
  firing rate climbs past cutoff (cruise/high rpm) they genuinely blend
  into a continuous roar, the way a muffler's resonant cavity actually
  behaves. Verified numerically: at cruise/high rpm the fraction of
  near-silent samples between pulses drops from ~20% to ~3%.
- **Turbo**: a whine whose pitch rises with spool fraction (`boost_bar /
  max_boost_bar`) *and* whose whole pitch range and gain depend on which
  turbo is actually fitted, not just how spooled it currently is -- a
  bigger turbo (higher `max_boost_bar`, a stand-in for compressor/turbine
  size) spins slower at full chat than a small one, so it gets a lower,
  more "whoosh" pitch range; and loudness scales with the actual boost
  *pressure* reached, not just relative spool fraction, so a big turbo
  genuinely making 2 bar reads as a more prominent sound event than a small
  one topping out at 0.7 bar even though both are "100% spooled." This is
  what makes the different turbo choices below audibly differ, not just
  produce different dyno numbers.

`EngineSpec.firing_order` is the same data both audio and the physics model
consume -- audio is a consumer of engine facts, not a separate system that
guesses from cylinder count alone.

### Realism pass: charge heat, boost/AFR tables, rev-limiter bounce, knock

Five additions on top of the original validated model, all bounded so the
three validated curves stay within their existing tolerances:

- **Charge-air heat soak** (`Turbo.tick()`) -- intake air temp chases
  `ambient + charge_temp_rise_k_per_bar * current_boost_bar` on its own
  (slow, ~10s) thermal lag, separate from the boost-pressure lag itself. A
  sustained WOT hold genuinely gets hotter the longer it's held -- verified
  in the CLI: ~20s at WOT on the B58 climbed intake air temp from ~40C to
  ~63C. Back-to-back pulls run hotter than a single cold pull because
  `Turbo.reset()` deliberately does *not* reset this state (only the boost
  gauge) -- an intercooler doesn't forget either.
- **RPM/load-based wastegate duty** (`ECU.wastegate_duty()`) -- the ECU no
  longer targets full boost authority unconditionally; it ramps in with
  load (previous tick's `load_fraction`, since this tick's isn't known yet)
  and with RPM (held back near idle even at WOT, for driveability/knock
  margin). Reaches 1.0 well before every validated spool checkpoint, so
  every existing WOT pull is bit-for-bit unaffected -- this only matters at
  partial throttle, which the throttle slider now makes reachable.
- **RPM/load-based AFR** (`ECU.target_afr()`) -- replaced the old
  throttle-position-only linear ramp with one indexed on `load_fraction`
  (MAP-based), matching how real speed-density ECUs actually index their
  base fuel table. Identical at WOT (both reach ~12.5 AFR), different at
  partial throttle.
- **Rev-limiter bounce** (`ECU.rev_limiter_active()`) -- fuel cut now has
  hysteresis (resumes only `_rev_limiter_bounce_band_rpm` below the cut
  point, not the instant rpm dips under it), so holding WOT into the
  limiter genuinely bounces rpm back and forth instead of flatlining dead
  level or chattering at one boundary -- audible live through
  `dyno_audio.gd` since it just reads `controller.rpm` every frame.
- **Knock/octane model** (`Engine._knock_efficiency_penalty()`, live-
  overridable via `octane`/`set_octane_override()`) -- running below an
  engine's `knock_octane_requirement` (approximate, not a literal published
  figure) costs thermal efficiency, but only under real load -- idling on
  bad fuel costs nothing, WOT on 10 points under costs up to ~15% torque.
  LS2 (89 octane, NA) is deliberately less sensitive than the two turbo
  presets (91 octane each) -- a real point of contrast between them.

**Turbo spool is also now firing-order-derived, not just hand-tuned**
(`Turbo._compute_pulse_quality()`): crank-degrees between exhaust pulses
sharing one turbine path (`720 / (cylinders / exhaust_scroll_groups)`)
narrows or widens the existing tuned `spool_width_rpm`/`spool_time_constant_s`
around a single-scroll-I4 reference (`pulse_quality == 1.0`, so EA888/IS20 is
completely unchanged). The B58's twin-scroll housing splits its actual
firing order (1-5-3 / 6-2-4) into two paths spaced 240 degrees apart instead
of one path at 120 degrees -- `pulse_quality ≈ 1.33`, genuinely derived from
`EngineSpec.firing_order_resolved` (the same ground truth `dyno_audio.gd`
consumes) rather than being a second, disconnected hand-picked constant.

### Off-throttle: coasts down under real engine braking, not just drag

Lifting mid-pull used to just gently decay on the dyno's ~3Nm parasitic drag
alone -- barely perceptible over tens of seconds, nothing like how a real
engine actually decelerates on a dyno. Two things were compounding to hide
real engine braking:

- **`ParametricEngine.compute()` floored net torque at 0.** A real engine
  brakes itself whenever friction exceeds indicated torque (near-zero
  fueling off-throttle) -- flooring it threw that away. Removed; harmless to
  every validated WOT curve (indicated torque there is always far larger
  than FMEP-scale friction, so the floor never actually bit during normal
  operation -- it only mattered at zero fueling).
- **The idle-air-equivalent fueling had no rpm ceiling.** It was tuned to
  produce modest, non-stalling torque *at idle rpm* -- applied unchanged at,
  say, 6000rpm off-throttle, the same small manifold pressure still flows
  (and burns) far more air at the higher pumping rate, making enough torque
  to stay net-positive and never decelerate at all. Real ECUs solve this
  with **DFCO** (deceleration fuel cut-off): closed throttle is only treated
  as idle-air up to `ECU.dfco_reengage_rpm` (`idle_rpm * 1.2`) -- above it,
  fuel cuts entirely, same as the rev limiter, and real engine braking (now
  that it isn't floored) does the decelerating.

`DynoSession._drive()` hands off from free_accel (coasting under engine
braking + dyno inertia) to the idle-hold PID at that *exact same*
`dfco_reengage_rpm`, deliberately -- if the PID engaged earlier, its
correction would stack on top of the engine's own still-active braking
torque and produce an unrealistically hard combined brake. One shared
threshold, not two hand-tuned constants that could drift apart.

**A second, subtler bug turned up writing the regression test for this:**
`DynoBrake.reset_pid()` always zeroed `_prev_error` to 0.0, regardless of
the *actual* rpm-vs-target error at the moment of reset. Handing off to the
PID from, say, 960rpm against an 800rpm idle target (a real 160rpm error)
made the very next tick's derivative term see a fake jump from 0 to 160 --
a textbook PID "derivative kick" -- spiking brake torque well past even the
already-firm proportional correction, still crashing rpm on handoff.
`reset_pid()` now takes an optional `prev_error` so `DynoSession` can seed
it with the real error, keeping the derivative term at ~0 on the first tick
instead of a phantom spike (`tests/test_components.py::test_dyno_brake_reset_pid_seeds_derivative_baseline_to_avoid_kick`
locks this in specifically).

### Idle: holds 800rpm, doesn't stall or run away (fixed, worth knowing why)

Two related bugs showed up back to back and are both fixed in
`engine_sim/core/ecu.py` and `engine_sim/session.py`:

1. **RPM settling around 6500 at "idle" instead of near zero.** Root cause:
   `ECU.intake_manifold_pressure()` only ever *added* boost scaled by
   throttle -- it never modeled the throttle plate restricting airflow at
   closed throttle, so 0% threshold still breathed at full atmospheric
   pressure and produced real torque (verified: ~118Nm) against only ~3Nm of
   dyno parasitic drag. Nothing stopped it climbing to the rev limiter.
   `intake_manifold_pressure()` now blends from a closed-throttle vacuum
   floor (`IDLE_MAP_PA`, ~30kPa) up to atmospheric as throttle opens --
   unchanged at WOT (throttle=1), so the validated power-pull curve is
   bit-for-bit identical.
2. That alone wasn't enough on its own (a fixed idle-air opening still needs
   *something* to hold it at a target RPM -- too much authority and it
   climbs, too little and it stalls, and there's no way to land exactly on
   zero net torque by tuning constants alone). The real fix: the ECU always
   applies a small, fixed idle-air-control opening at zero throttle
   (`idle_throttle_equivalent`, modest torque, never cut) and
   `DynoSession.tick()` uses the dyno brake's existing `hold_rpm` PID
   (`SimulationLoop`/`DynoBrake`, already built for exactly this) to hold
   RPM at `idle_rpm_target` (800rpm, `EA888_GEN3_IS20.idle_rpm`) against it --
   the same way a real idle is also held against accessory/AC-compressor
   load, not by tuning the engine to balance itself unaided. Recovers
   smoothly back to ~800rpm after a power pull too, not just on startup.

Covered by `tests/test_components.py::test_zero_throttle_uses_bounded_idle_air_not_full_atmospheric_map`
and `tests/test_session.py::test_session_starts_at_idle_and_holds_it` /
`::test_idle_recovers_after_a_power_pull`.

### A pull now actually resists the engine, instead of free-revving

An active power pull used to run `free_accel` (~3Nm of dyno drag, essentially
unloaded) -- realistic for casual free-play, but a real engine dyno's whole
job is to *load* the engine, not let it rev against nothing. During an
active pull the brake now runs `ramp_rpm` instead: it actively resists to
hold a controlled sweep pace (up to 400rpm/s at full throttle, scaling down
with it, matching `SimulationLoop.run_power_pull()`'s own default and real
dyno sweep rates) -- at WOT this soaks up hundreds of Nm of resistance, not
3. Outside of an active/recorded pull (casual free-play, e.g. the CLI's
`throttle`/`step`), it's still plain `free_accel` -- only a recorded pull
gets the resisted, paced sweep.

### Audited: dead code, comment accuracy, and mutation-tested assertions

A full pass over the project rather than just trusting green tests:

- **Dead code**: an AST-based scan of every function/method across
  `engine_sim`, `dyno_cli.py`, and the Godot scripts found nothing unused.
  An unused `import pytest` in `tests/test_cli.py` was the one real find,
  removed.
- **Comment accuracy**: several stale references were found and fixed --
  `Turbo.reset()` pointed at `EngineSpec.charge_temp_rise_k_per_bar`
  (actually a `TurboSpec` field), `specs.py` referenced a nonexistent
  `Turbo._pulse_quality()` method (it's `_compute_pulse_quality()`), and
  three module docstrings (`core/dyno.py`, `session.py`,
  `dyno_controller.py`) still described a planned "drag-strip view" future
  consumer -- stale now that there's no such roadmap (see "Not built, and
  not currently planned" below). `dyno_controller.py`'s own class docstring
  had also drifted: it listed only the original inputs and never mentioned
  `octane_override`/`throttle_percent` once those were added.
- **Mutation testing** (deliberately breaking one piece of logic at a time,
  confirming the suite goes red, then reverting) against rev-limiter
  hysteresis, the AFR control law, the knock-penalty guard, the VE floor,
  `pulse_quality`'s clamp bounds, wastegate duty's rpm term, the FMEP
  friction sign, the engine-braking floor, and the pull-resistance fix above
  -- all caught cleanly by a single, correctly-targeted test each. One
  mutation (disabling DFCO by inflating `_dfco_reengage_factor`) initially
  passed clean -- a real false negative: the existing DFCO test read
  `ecu.dfco_reengage_rpm` as its own reference point rather than asserting
  what that number should actually be, and the coast-down regression test
  only ever compared *among* post-lift samples, never against the rpm right
  before lifting -- exactly where that mutation's crash-to-zero landed.
  Both gaps are fixed: `test_dfco_reengage_rpm_is_pinned_to_a_real_value_not_just_self_consistent`
  now pins the actual number, and the coast-down test seeds its sample list
  with the pre-lift rpm.

## Not built, and not currently planned

Transmission and drag-strip mode (wheelspin, rolling resistance/tire friction
-- deliberately *not* modeled in dyno mode). There's no roadmap toward these
right now -- current work is optimization and realism on the dyno model
itself (new validated engine/turbo presets, tighter physical modeling,
audio), not new phases or scope.
