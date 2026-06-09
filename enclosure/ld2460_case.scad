// ld2460_case.scad — HLK-LD2460 monitor-top enclosure (parametric, mm)
// Render: openscad -D part="shell" | "lid" | "all" -o out.stl ld2460_case.scad
// Frame: X=width (centred), Y=depth (front at 0, screen at +Y), Z=up (foot base at 0)

part = "all";          // "shell" | "lid" | "all"
$fn = 48;

/* ----- Measured / to-confirm (defaults are placeholders) ----- */
ld2460_w     = 32;     // PCB width  (X)
ld2460_h     = 49.5;   // PCB height (Z)
ld2460_t     = 1.2;    // PCB thickness            [MEASURE]
comp_height  = 5.0;    // front parts incl. perpendicular connectors [CONFIRM]
ch343_l      = 26;     // CH343P long edge (across X)
ch343_w      = 13;     // CH343P short edge (along Y)
ch343_t      = 1.2;    // CH343P thickness         [MEASURE]
usb_w        = 9.5;    // Type-C cutout width      [MEASURE]
usb_h        = 4.0;    // Type-C cutout height     [MEASURE]
screen_edge_t = 12;    // monitor top-edge thickness [MEASURE]

/* ----- Design / fit ----- */
wall         = 2.0;
window_wall  = 1.2;    // thin RF face
window_clear = 1.0;    // gap beyond comp_height to inner window
back_gap     = 2.0;    // behind PCB (solder side)
fit_clear    = 0.4;    // board/lid slip fit
tilt_deg     = 12;     // antenna look-down tilt
connector_clear = 12;  // perpendicular room for the plugged harness
foot_extra_depth = 4;  // foot margin behind CH343P
hook_lip_h   = 18;     // lip drop behind screen
hook_wall    = 2.5;
hook_clear   = 1.5;    // slip over the screen edge
snap_w       = 8;
snap_t       = 1.6;
snap_hook    = 1.0;
lid_t        = 2.0;
vent         = true;

/* ----- Derived ----- */
cav_w     = ld2460_w + 2 * fit_clear;          // inner width
out_w     = cav_w + 2 * wall;                  // outer width
front_gap = comp_height + window_clear;        // board front -> window inner
up_in_d   = front_gap + ld2460_t + back_gap;   // upright inner depth (Y)
up_out_d  = window_wall + up_in_d;             // upright outer depth (back open)
board_margin = 3;
up_h      = ld2460_h + 2 * board_margin;       // upright inner height (board + slack)
foot_h    = wall + max(ch343_t + usb_h, 6) + 1;
foot_depth = up_out_d + ch343_w + foot_extra_depth + wall;
// The tilted upright must sink into the foot so the two weld into one solid
// (a flat-on-tilted contact would only touch along an edge -> non-manifold).
plunge    = up_out_d * sin(tilt_deg) + 2;

// Hollow interior of the upright (board + clearances); thin window stays at the
// front, side walls remain, back stays open for the lid.
module ld2460_board_cavity() {
    translate([wall, window_wall, wall])
        cube([out_w - 2 * wall, up_in_d + 1, up_h - 2 * wall]);
}

// Per-side rib pairs that form a vertical groove gripping the left/right PCB
// edges. Each rib overlaps its side wall (for a clean manifold weld) and
// protrudes into the cavity; the front/back rib pair captures the board edge in
// Y at the board's front-face position (so the antenna sees the window).
module ld2460_edge_slots() {
    slot_y = window_wall + front_gap;          // board front face (Y)
    protrude = 1.2;                            // how far ribs reach into cavity
    rib_t = 1.0;                               // rib thickness in Y
    z0 = wall + 1;
    zh = up_h - 2 * wall - 2;
    // left side: overlap the left wall, protrude into the cavity (+X)
    for (ry = [slot_y - rib_t, slot_y + ld2460_t + fit_clear])
        translate([wall - 1.2, ry, z0]) cube([protrude + 1.2, rib_t, zh]);
    // right side: overlap the right wall, protrude into the cavity (-X)
    for (ry = [slot_y - rib_t, slot_y + ld2460_t + fit_clear])
        translate([out_w - wall - protrude, ry, z0]) cube([protrude + 1.2, rib_t, zh]);
}

module foot_interior() {
    translate([wall, wall, wall])
        cube([out_w - 2 * wall, foot_depth - 2 * wall, foot_h]);  // open top
}

// Cut (in the upright local frame): opens the cavity floor down through the
// plunge into the foot interior so the perpendicular harness plugs and the 4
// wires route from the board's connector edge down to the CH343P.
module wire_channel() {
    cw = cav_w * 0.7;
    translate([(out_w - cw) / 2, window_wall, -plunge - 2])
        cube([cw, up_in_d, wall + plunge + 4]);
}

// Additive U of retaining ribs in the foot floor that locate the CH343P (flat,
// long edge across X, short edge along Y, Type-C toward the back/+Y, open at the
// back for the lid's USB cutout).
module ch343_pocket() {
    pw = ch343_l + 2 * fit_clear;
    pd = ch343_w + 2 * fit_clear;
    py = up_out_d + 1;             // pocket front, just behind the upright base
    rib = 1.5;
    rh = ch343_t + 2;
    translate([-pw / 2 - rib, py, wall - 0.5]) cube([rib, pd, rh]);            // left
    translate([pw / 2, py, wall - 0.5]) cube([rib, pd, rh]);                   // right
    translate([-pw / 2 - rib, py - rib, wall - 0.5]) cube([pw + 2 * rib, rib, rh]);  // front
}

module shell() {
    difference() {
        union() {
            translate([-out_w / 2, 0, 0]) cube([out_w, foot_depth, foot_h]);
            translate([0, 0, foot_h])
                rotate([tilt_deg, 0, 0])
                    translate([-out_w / 2, 0, -plunge])
                        cube([out_w, up_out_d, up_h + plunge]);
        }
        translate([-out_w / 2, 0, 0]) foot_interior();
        translate([0, 0, foot_h])
            rotate([tilt_deg, 0, 0])
                translate([-out_w / 2, 0, 0]) ld2460_board_cavity();
        translate([0, 0, foot_h])
            rotate([tilt_deg, 0, 0])
                translate([-out_w / 2, 0, 0]) wire_channel();
    }
    translate([0, 0, foot_h])
        rotate([tilt_deg, 0, 0])
            translate([-out_w / 2, 0, 0]) ld2460_edge_slots();
    ch343_pocket();
}
module lid()   { /* defined in a later task */ }

if (part == "shell") shell();
else if (part == "lid") lid();
else { shell(); }
