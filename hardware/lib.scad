// Shared pieces for the AudioTarget enclosures. Units: mm.
// Print in PETG or ASA (PLA softens in a hot car), 0.2 mm layers, 4 walls.

$fn = 48;
clear = 0.25;   // fit clearance; raise to 0.3-0.4 if parts are too tight

// ---------------------------------------------------------------- Picatinny
// MIL-STD-1913 cross-section: 15.67 mm flat top, 45 degree flanks out to
// 21.2 mm at 2.77 mm down, then back in at 45 degrees.
rail_top_w   = 15.67;
rail_crest_w = 21.2;
rail_crest_d = 2.77;
rail_slot_w  = 5.23;   // cross slots, 10.01 mm pitch
rail_slot_p  = 10.01;

// Rail profile (with clearance) as seen from the muzzle; z=0 is the top of the rail.
module rail_profile(c = clear) {
    t = rail_top_w / 2 + c;
    k = rail_crest_w / 2 + c;
    polygon([[-t, 0 + c], [t, 0 + c], [k, -rail_crest_d], [t, -2 * rail_crest_d],
             [t, -20], [-t, -20], [-t, -2 * rail_crest_d], [-k, -rail_crest_d]]);
}

// Slide-on clamp. Its top face is at z = roof (sits roof mm above the rail).
// A cross bolt (M4) runs through a rail slot to lock it and squeeze the jaws.
module rail_clamp(len = 30, width = 30, roof = 4, bolt_at = 15) {
    jaw_depth = rail_crest_d + 2.2;     // jaws hook under the crest
    difference() {
        translate([-width / 2, 0, -jaw_depth]) cube([width, len, jaw_depth + roof]);
        // the rail
        rotate([90, 0, 0]) translate([0, 0, -len - 1])
            linear_extrude(len + 2) rail_profile();
        // cross bolt, nut trap one side, head counterbore the other
        translate([0, bolt_at, -0.9]) rotate([0, 90, 0]) {
            cylinder(d = 4.4, h = width + 2, center = true);
            translate([0, 0, width / 2 - 3]) cylinder(d = 8.1, h = 4, $fn = 6);
            translate([0, 0, -width / 2 - 1]) cylinder(d = 7.8, h = 4);
        }
        // relief cut so the jaws can flex onto the rail
        translate([-0.75, -1, roof - 1.2]) cube([1.5, len + 2, 2]);
    }
}

// ---------------------------------------------------------------- boxes
module rounded_box(size, r = 3) {
    hull() for (x = [r, size.x - r], y = [r, size.y - r])
        translate([x, y, 0]) cylinder(r = r, h = size.z);
}

// Open-top box with inner size `inner`, wall `w`, floor `f`.
module tray(inner, w = 2, f = 2, r = 3) {
    difference() {
        rounded_box([inner.x + 2 * w, inner.y + 2 * w, inner.z + f], r);
        translate([w, w, f]) rounded_box([inner.x, inner.y, inner.z + 1], max(r - w, 0.5));
    }
}

// Lid with a lip that drops inside the tray.
module lid(inner, w = 2, t = 2, lip = 2.5, r = 3) {
    rounded_box([inner.x + 2 * w, inner.y + 2 * w, t], r);
    translate([w + clear, w + clear, -lip])
        difference() {
            rounded_box([inner.x - 2 * clear, inner.y - 2 * clear, lip], max(r - w, 0.5));
            translate([1.2, 1.2, -1]) rounded_box([inner.x - 2 * clear - 2.4, inner.y - 2 * clear - 2.4, lip + 2], 0.5);
        }
}

// Screw post for an M2.5 (or M2) self-tapping screw.
module post(h, d = 5.5, hole = 2.2) {
    difference() { cylinder(d = d, h = h); translate([0, 0, 1]) cylinder(d = hole, h = h); }
}

// Tactile dimples, for subtracting from a top surface at z=0 (lids print
// top-face-down, so raised marks would sit on the print bed).
module dimples(n, pitch = 3.5, d = 2.2, depth = 0.9) {
    for (i = [0 : n - 1]) translate([i * pitch - (n - 1) * pitch / 2, 0, -depth])
        cylinder(d = d, h = depth + 1, $fn = 20);
}
