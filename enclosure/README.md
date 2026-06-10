# LD2460 Monitor-Top Enclosure

Parametric OpenSCAD case that perches the HLK-LD2460 (+ CH343P USB-serial bridge)
on a monitor's top edge, antenna facing the room at a slight downward tilt. Two
printed parts: a front **shell** and an L-shaped **lid** (closes the upright back
and the foot top).

> Status: a parametric first cut, verified to render manifold (clean STL). Fit
> tolerances, lid retention, and the screen-hook gap should be confirmed with a
> test print and then tuned in the parameters — that is the point of keeping it
> parametric.

## Render / export

```bash
# Preview in the GUI
openscad enclosure/ld2460_case.scad

# Export each printable part to STL (binary)
openscad -D 'part="shell"' --export-format binstl -o shell.stl enclosure/ld2460_case.scad
openscad -D 'part="lid"'   --export-format binstl -o lid.stl   enclosure/ld2460_case.scad
```

`part` selects `"shell"`, `"lid"`, or `"all"` (assembled preview). Override any
parameter with `-D name=value` (e.g. `-D 'tilt_deg=8'`).

## Measure these before printing

The defaults render, but confirm against your hardware (edit the top of
`ld2460_case.scad`):

- `ld2460_t` — LD2460 PCB thickness.
- `comp_height` — tallest front-side stack **including the perpendicular header
  pins** (≈ 5 mm). The wires plug in perpendicular, so `connector_clear` reserves
  room below for the plugs; they route down the `wire_channel` to the CH343P.
- `ch343_t`, `usb_w`, `usb_h` — CH343P PCB thickness and Type-C connector size
  (module is ~26 × 13 mm).
- `screen_edge_t` — your monitor's top-edge thickness; sets where the rear hook
  lip drops. `hook_clear` is the slip gap; `hook_lip_h` how far it hangs.
- `tilt_deg` — antenna look-down angle (default 12°; the upright leans toward the
  room so the antenna aims slightly down).
- `fit_clear` — slip fit for the boards and lid (raise if parts are tight).

## Assembly

1. Drop the CH343P into the foot pocket (Type-C toward the rear cutout).
2. Slide the LD2460 into the upright, antenna toward the front window; run the
   4-wire harness (pins 1, 2, 7, 8) down the wire channel to the CH343P.
3. Fit the L-lid over the upright back + foot top.

The lid is currently a press-fit cover. Secure it with a dab of glue, a strip of
tape, or add snap tabs / small screw bosses once you have measured the printed
fit — these are easy to add to `module lid()`.

## Print settings

- Material: **PETG / ASA / ABS** (avoid PLA near a warm/sunny screen).
- Shell printed **window-face-down** (smooth RF face, fewest supports); lid flat.
- 0.2 mm layers, 3 perimeters, 20–30% infill.
- Keep the front (window) face free of metal/metallic paint — 24 GHz passes
  through thin plastic, not metal.

See `../docs/hardware-enclosure-notes.md` for wiring, pinout, and board data.
