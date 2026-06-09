# LD2460 Monitor-Top Enclosure — Design

Date: 2026-06-09

## Purpose

A 3D-printable enclosure that perches the HLK-LD2460 radar (plus its CH343P
USB-serial bridge) on the **top edge of a monitor/screen**, antenna facing the
room at a slight downward tilt — a radar "webcam". Produced as a **parametric
OpenSCAD model** so every dimension can be tuned after measuring the actual
hardware, then rendered/exported to STL in OpenSCAD (free) and printed.

Companion hardware reference: `docs/hardware-enclosure-notes.md`.

## Form factor & layout

A compact wedge / "L". An **upright front housing** tilted ~12° back holds the
LD2460 portrait (32 mm wide × 49.5 mm tall) so its 120° horizontal field of view
sweeps across the room and the antenna faces the room through the front face. A
shallow **base/foot** extends rearward, rests on the screen's top edge, and houses
the CH343P lying flat (Type-C toward the rear). A **rear lip hooks down behind
the screen** so the unit can't slide forward. The Type-C cable exits straight
**down the back**.

```
  front (room)                         back (behind screen)
       ___
      /   \   ← LD2460, antenna face = thin RF window, tilted ~tilt_deg
     / [#] \
    | LD2460 |   (component/connector side faces the window; ~5 mm of parts
    | board  |    incl. PERPENDICULAR header pins + plugged wires)
     \______/____________________________
    |  foot  [ CH343P flat ]       | hook |
    |________________ rests on top |  ||  | ← lip drops behind the screen
                       of screen   |  ||  |
                         USB-C  ↓ exits down the back
```

The CH343P sits **below and behind the antenna plane** so it is out of the
24 GHz beam.

## Two printed parts (snap-fit, no screws)

1. **Front shell** — the tilted upright with the thin RF window, side and top
   walls, the foot floor, and the rear hook. Open at the back for assembly.
2. **Rear lid** — snaps into the shell from behind, closing the foot; carries the
   Type-C cutout (lower rear) and the cable exit slot.

Closure is by **cantilever snap catches** on the lid engaging lugs in the shell
(parametric). No screws, no threaded inserts.

## Board retention (no screws; does not rely on unmeasured mounting holes)

- **LD2460:** retained by **edge slots/ribs** that grip the left/right PCB edges,
  with a ledge that sets the standoff between the board's component side and the
  front window. PCB thickness is a parameter.
- **CH343P:** drops into a **26 × 13 mm pocket** in the foot with a retaining rib;
  a **Type-C cutout** in the rear lid aligns to its connector. PCB thickness and
  connector size/offset are parameters.

## Connector & perpendicular-clearance handling (important)

The LD2460's component/connector side stacks to **~5 mm**, and the wire **headers
stand perpendicular to the board** — the mating Dupont/JST plugs therefore project
perpendicular off that face and the wires must bend away. The model accounts for
this in two ways:

- The **front cavity depth** (board face → inside of window) =
  `comp_height + window_clear` so the window never touches the tallest part.
- A parametric **connector keep-out + wire channel**: at the board's connector
  edge (default the **bottom edge**, nearest the foot) the cavity opens into the
  foot, reserving `connector_clear` of perpendicular space for the plugged
  harness and routing the 4 wires (pins 1, 2, 7, 8) down to the CH343P. The
  connector-zone position/size are variables, since exact header positions
  should be confirmed on the board.

This keeps the general antenna gap small while giving the perpendicular plugs the
depth they need only where the connectors actually are.

## RF window

The **entire front face is thin plastic** (`window_wall`, default ~1.2 mm) with no
metal and an air gap to the antenna — 24 GHz passes cleanly through PETG/ABS/ASA.
No metallic paint/foil over this face. (Datasheet: signals penetrate thin
plastic; not metal.)

## Parameters (all top-of-file; defaults render immediately)

**MEASURE on your hardware (defaults are placeholders):**
- `ld2460_w = 32`, `ld2460_h = 49.5` — PCB outline (from datasheet, confirm).
- `ld2460_t = 1.2` — LD2460 PCB thickness. **Measure.**
- `comp_height = 5.0` — tallest stack on the component side **including the
  perpendicular connector bodies**. (Per user.) **Confirm.**
- `connector_clear = 12.0` — extra perpendicular room for the plugged wire
  connectors at the connector zone. **Confirm against your plugs.**
- `connector_zone` — position/size of the header keep-out (default: full width
  along the bottom edge). **Confirm header positions (pins 1,2,7,8).**
- `ch343_l = 26`, `ch343_w = 13`, `ch343_t = 1.2` — CH343P PCB. **Measure thickness.**
- `usb_w`, `usb_h`, `usb_z_offset` — Type-C cutout size and height off the foot
  floor. **Measure the module's connector.**
- `screen_edge_t = 12` — thickness of your screen's top edge (sets hook gap).
  **Measure your monitor.**

**Design/fit (sane defaults):**
- `wall = 2.0`, `window_wall = 1.2`, `window_clear = 1.0` (gap beyond comp_height).
- `fit_clear = 0.4` — slip fit for boards/lid.
- `tilt_deg = 12` — front-housing backward tilt.
- `hook_depth`, `hook_lip_h`, `hook_clear` — rear hook geometry.
- `snap_w`, `snap_depth`, `snap_thickness` — cantilever snap features.
- `vent` (bool) — optional slots in the foot for the ≤1.3 W thermal load.
- `$fn` — curve resolution.

`assert()` statements guard impossible combinations (e.g. negative cavities,
window thinner than a nozzle width).

## OpenSCAD structure (`enclosure/ld2460_case.scad`)

- Parameter block at top.
- `part = "all" | "shell" | "lid"` switch selecting what to render (so each piece
  can be exported separately; `"all"` shows the assembled view for inspection).
- Modules: `front_shell()`, `rear_lid()`, and helpers `ld2460_pocket()`,
  `antenna_window()`, `ch343_pocket()`, `usb_cutout()`, `rear_hook()`,
  `wire_channel()`, `snap_catch()` / `snap_lug()`, `vent_slots()`.
- Each helper has one clear responsibility and is driven only by the parameters.

## Print settings (documented, not enforced)

- Material: **PETG / ASA / ABS** (avoid PLA if near a warm/sunny screen).
- Front shell printed **window-face-down** (smooth RF face, minimal supports);
  rear lid printed flat. Snap cantilevers oriented to avoid layer-split.
- 0.2 mm layers, 3 perimeters, 20–30% infill — adequate for this small load.

## Deliverables & file structure

```
enclosure/
  ld2460_case.scad     # parametric model (part switch: all/shell/lid)
  README.md            # parameters, measurement checklist, print + export steps
```
If the `openscad` CLI is available on this machine, the build will also render
`enclosure/ld2460_shell.stl`, `enclosure/ld2460_lid.stl`, and a preview PNG, and
verify the model renders without errors / is manifold. Otherwise these are
produced by the user in the OpenSCAD GUI. (STL/PNG outputs are git-ignored;
`*.stl`/`*.png` artifacts are not committed — the `.scad` source is.)

## Verification

- `openscad -o /tmp/x.stl --hardwarnings ld2460_case.scad` for each `part` value
  renders with **no warnings/errors** (CGAL manifold).
- Sanity asserts on key dimensions (outer size ≈ board + 2·wall + gaps; window
  gap ≥ comp_height; hook gap ≥ screen_edge_t).
- Visual check of the `"all"` assembled render (PNG) for clearances and the
  board/USB/hook relationships.

## Out of scope

- Exact LD2460 mounting-hole bosses (we use edge retention; holes unmeasured).
- A second mounting variant (wall/ceiling) — this case targets monitor-top only;
  the `.scad` stays parametric enough to fork later.
- Cable strain-relief hardware beyond the exit slot geometry.
