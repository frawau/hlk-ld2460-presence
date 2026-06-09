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

module body_blank() {
    // Foot slab on the screen
    translate([-out_w / 2, 0, 0]) cube([out_w, foot_depth, foot_h]);
    // Upright at the foot front, tilted so the antenna looks slightly DOWN
    // (positive tilt_deg leans the top toward the room / -Y).
    translate([0, 0, foot_h])
        rotate([tilt_deg, 0, 0])
            translate([-out_w / 2, 0, 0]) cube([out_w, up_out_d, up_h]);
}

module shell() { body_blank(); }
module lid()   { /* defined in a later task */ }

if (part == "shell") shell();
else if (part == "lid") lid();
else { shell(); }
