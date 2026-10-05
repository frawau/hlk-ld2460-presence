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

# Export each printable part to STL (binary), oriented for the print bed
openscad -D 'part="shell"' -D 'layout="print"' --export-format binstl -o shell.stl enclosure/ld2460_case.scad
openscad -D 'part="lid"'   -D 'layout="print"' --export-format binstl -o lid.stl   enclosure/ld2460_case.scad
```

`layout="print"` lays the shell window-face-down and the two lid panels flat,
side by side. Omit it (default `layout="assembled"`) to export parts as they sit
on the monitor.

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
- `landscape` — board orientation in the upright. `true` (default) lays the
  LD2460 long edge (49.5 mm) horizontal; `false` stands it portrait.
- `fit_clear` — slip fit for the boards and lid (raise if parts are tight).

## Assembly

1. Drop the CH343P into the foot pocket (Type-C toward the rear cutout).
2. Slide the LD2460 into the upright, antenna toward the front window; run the
   4-wire harness (pins 1, 2, 7, 8) down the wire channel to the CH343P.
3. Fit the L-lid over the upright back + foot top.

The lid's back panel drops into the upright's open back, behind the rear board
ribs (which stop it), leaving `back_gap` behind the board. Each lid panel is
`fit_clear` smaller than its opening (`fit_clear / 2` per side), so it is a slip
fit, not a press fit: secure it with a dab of glue, a strip of tape, or add snap
tabs / small screw bosses once you have measured the printed fit — these are
easy to add to `module lid()`.

## Print settings

- Material: **PETG / ASA / ABS** (avoid PLA near a warm/sunny screen).
- Shell printed **window-face-down** (smooth RF face); lid panels flat. Use the
  `layout="print"` exports above.
- Shell supports: the rear hook lip lies almost flat ~8 mm above the bed (support
  from the build plate), and the inside of the foot's rear wall is a ceiling over
  the foot cavity (support inside, removed through the open foot top). The
  board-edge ribs and the CH343P rib are short ledges and need none.
- 0.2 mm layers, 3 perimeters, 20–30% infill.
- Keep the front (window) face free of metal/metallic paint — 24 GHz passes
  through thin plastic, not metal.

See `../docs/hardware-enclosure-notes.md` for wiring, pinout, and board data.
