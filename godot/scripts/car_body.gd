extends Node2D
## Car silhouette -- static shape, drawn once, in the Car node's own local
## space (origin sits on the road surface, midway between the wheels; +x is
## forward/right, -y is up). Purely decorative: drag_race.gd never touches
## this node directly, only the wheel children (for rotation) and the
## smoke children (for wheelspin).
##
## Shaped and liveried specifically as a Mk7 Golf GTI (the scene's default/
## canonical car, see DynoSession() -- other CAR_CHOICES entries share this
## same silhouette rather than each getting their own, same as before this
## file existed): a short front overhang and low sloped hood, steep upright
## windshield, long flat hatchback roofline into a short, steep hatch (no
## saloon trunk), a small integrated roof-edge lip spoiler rather than a
## big strutted wing, GTI's signature red grille stripe running through the
## headlights, black honeycomb-grille/rocker-cladding trim, and dual rear
## exhaust tips (Performance Pack cue). Nose/tail extents (HALF_WHEELBASE +-
## 50/45) are unchanged from this file's previous, more generic silhouette
## so drag_scene_layout.gd's PIXELS_PER_METER calibration comment (anchored
## to this sprite's 225px nose-to-tail span) and _draw_shadow()'s ellipse
## both stay correct without needing their own edit.

const Layout = preload("res://scripts/drag_scene_layout.gd")

const BODY_COLOR := Color(0.92, 0.92, 0.94)  # Pure White -- a common, high-contrast GTI color
const WINDOW_COLOR := Color(0.32, 0.42, 0.52, 0.92)
const TRIM_COLOR := Color(0.08, 0.08, 0.1)  # grille/rocker cladding/spoiler/mirror/exhaust -- gloss black
const RED_ACCENT_COLOR := Color(0.82, 0.06, 0.06)  # GTI's signature grille stripe
const HEADLIGHT_COLOR := Color(0.9, 0.92, 0.78, 0.95)
const SHADOW_COLOR := Color(0.0, 0.0, 0.0, 0.35)

const HALF_WHEELBASE := Layout.CAR_WHEELBASE_PX * 0.5
const RIDE_HEIGHT := Layout.WHEEL_RADIUS_PX  # chassis floor sits level with the wheel centers -- a low, drag-car ride height


func _draw() -> void:
	# A contact shadow, not just relying on the wheels touching y=0 exactly
	# -- without one the car reads as floating above the road even when the
	# geometry is pixel-flush, because there's no visual cue actually tying
	# it down to the ground plane. Drawn first (and so under everything
	# else this node and the wheel nodes draw -- see Car's own child order
	# in DragRace.tscn) so it sits beneath the body/wheels, not on top.
	_draw_shadow()

	var floor_y := -RIDE_HEIGHT

	# Main hatchback silhouette -- short overhangs, low hood, steep
	# windshield, long flat roof into a short steep hatch. Nose tip at
	# HALF_WHEELBASE+50, tail at -HALF_WHEELBASE-45 -- same envelope the
	# previous silhouette used (see this file's header).
	var body := PackedVector2Array([
		Vector2(-HALF_WHEELBASE - 45, floor_y),
		Vector2(-HALF_WHEELBASE - 45, floor_y - 16),
		Vector2(-HALF_WHEELBASE - 20, floor_y - 52),
		Vector2(-HALF_WHEELBASE + 15, floor_y - 62),
		Vector2(HALF_WHEELBASE - 35, floor_y - 62),
		Vector2(HALF_WHEELBASE - 10, floor_y - 40),
		Vector2(HALF_WHEELBASE + 35, floor_y - 34),
		Vector2(HALF_WHEELBASE + 50, floor_y - 16),
		Vector2(HALF_WHEELBASE + 50, floor_y),
	])
	draw_colored_polygon(body, BODY_COLOR)

	var window := PackedVector2Array([
		Vector2(HALF_WHEELBASE - 15, floor_y - 40),
		Vector2(HALF_WHEELBASE - 32, floor_y - 58),
		Vector2(-HALF_WHEELBASE + 12, floor_y - 59),
		Vector2(-HALF_WHEELBASE - 12, floor_y - 40),
	])
	draw_colored_polygon(window, WINDOW_COLOR)

	# Small integrated roof-edge lip spoiler -- a real GTI's own, not the
	# big strutted wing the previous silhouette had.
	draw_rect(Rect2(-HALF_WHEELBASE - 26, floor_y - 66, 20, 5), TRIM_COLOR)

	# Front grille block + GTI's own signature red stripe running through
	# the headlights, plus a headlight hint.
	draw_rect(Rect2(HALF_WHEELBASE + 16, floor_y - 28, 26, 14), TRIM_COLOR)
	draw_rect(Rect2(HALF_WHEELBASE + 12, floor_y - 30, 36, 4), RED_ACCENT_COLOR)
	draw_rect(Rect2(HALF_WHEELBASE + 38, floor_y - 32, 10, 6), HEADLIGHT_COLOR)

	# Side mirror.
	draw_rect(Rect2(HALF_WHEELBASE - 20, floor_y - 46, 8, 5), TRIM_COLOR)

	# Lower rocker/bumper cladding -- the two-tone black lower band common
	# on hot hatches, spanning the full silhouette width.
	draw_rect(Rect2(-HALF_WHEELBASE - 45, floor_y - 6, 225, 6), TRIM_COLOR)

	# Dual rear exhaust tips (Performance Pack cue).
	draw_circle(Vector2(-HALF_WHEELBASE - 40, floor_y - 2), 3.0, TRIM_COLOR)
	draw_circle(Vector2(-HALF_WHEELBASE - 30, floor_y - 2), 3.0, TRIM_COLOR)


func _draw_shadow() -> void:
	# Flattened ellipse at wheel-contact height (y=0, this node's own
	# origin), roughly spanning the car's own footprint plus a small margin
	# -- draw_colored_polygon has no ellipse primitive, so it's approximated
	# with a ring of points.
	var center_x := (HALF_WHEELBASE + 50 - HALF_WHEELBASE - 45) * 0.5
	var rx := HALF_WHEELBASE + 60.0
	var ry := 10.0
	var segments := 24
	var points := PackedVector2Array()
	for i in segments:
		var a := TAU * float(i) / float(segments)
		points.append(Vector2(center_x + cos(a) * rx, sin(a) * ry))
	draw_colored_polygon(points, SHADOW_COLOR)
