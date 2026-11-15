// Layout 2: Raspberry Pi Zero 2 W and camera together on the gun rail.
// The gun module box (nrf_box.scad) clamps on just behind this one; a short
// 3-wire cable joins them through the rear gland.
//
// Camera options (set `cam`):
//   "m12" - Camera Module 2-size board (25 x 24 mm, M2 holes 21 x 12.5 mm)
//           with an M12 lens mount, e.g. Arducam IMX219 M12. With a 12-16 mm
//           M12 lens this gives a narrow 13-17 degree view: good range, small box.
//   "hq"  - Raspberry Pi HQ camera (38 mm board, M2.5 holes on 30 mm square)
//           with a C/CS lens. Longest range, much bigger box.
// The camera bolts to the inside of the front wall, lens through the hole.
//
// Lid: three menu buttons (Up / Select / Down), same as the belt case.
include <lib.scad>

cam  = "m12";       // "m12" or "hq"
part = "both";      // "tray", "lid" or "both"

// Camera geometry: [board w, board h, hole dx, hole dz, hole d, lens hole d, lens z offset from hole centre]
C = cam == "hq" ? [38, 38, 30, 30, 2.7, 32, 0]
                : [25, 24, 21, 12.5, 2.2, 16, 0];

inner = cam == "hq" ? [44, 86, 44] : [36, 80, 30];
w = 2; f = 2;
zero = [30, 65];           // Pi Zero 2 W board (across, along)
zero_holes = [[3.5, 3.5], [26.5, 3.5], [3.5, 61.5], [26.5, 61.5]];
standoff = 3;
cam_z = f + inner.z / 2 + 2;   // camera hole-pattern centre height above the tray floor
clamp_len = 50;

module tray_part() {
    ox = -(inner.x + 2 * w) / 2;   // tray's left outer edge
    bx = ox + w + 1;               // board's left edge (port side, 1 mm from wall)
    by = w + 3;                    // board's rear edge
    difference() {
        union() {
            translate([ox, 0, 4]) tray(inner, w, f);
            rail_clamp(len = clamp_len, width = 30, roof = 4, bolt_at = 25);
            for (h = zero_holes)
                translate([bx + h.x, by + h.y, 4 + f]) post(standoff, 5, 2.2);
            for (x = [ox + w + 3, ox + w + inner.x - 3], y = [w + 3, w + inner.y - 3])
                translate([x, y, 4 + f]) post(inner.z - 0.5);
        }
        // Pi Zero ports (mini HDMI, USB data, USB power) through the left wall
        translate([ox - 1, by + 6, 4 + f + standoff + 1.2]) cube([w + 2, 54, 7]);
        // camera: lens hole and screw holes through the front wall
        translate([0, w + inner.y - 1, 4 + cam_z + C[6]]) rotate([-90, 0, 0])
            cylinder(d = C[5], h = w + 4);
        for (sx = [-1, 1], sz = [-1, 1])
            translate([sx * C[2] / 2, w + inner.y - 1, 4 + cam_z + sz * C[3] / 2])
                rotate([-90, 0, 0]) cylinder(d = C[4] + 0.3, h = w + 4);
        // rear cable gland to the gun module box
        translate([0, -1, 4 + f + 12]) rotate([-90, 0, 0]) cylinder(d = 6, h = w + 2);
        // side vents (right wall)
        for (i = [0 : 5]) translate([-ox - w - 1, 18 + i * 8, 4 + f + 6]) cube([w + 2, 3, 12]);
    }
}

module lid_part() {
    cx = w + inner.x / 2;
    ys = [w + inner.y - 16, w + inner.y / 2, w + 16];  // up (front), select, down (rear)
    difference() {
        lid([inner.x, inner.y, inner.z], w, 2);
        for (x = [w + 3, w + inner.x - 3], y = [w + 3, w + inner.y - 3])
            translate([x, y, -5]) cylinder(d = 2.8, h = 10);
        for (i = [0 : 2]) translate([cx, ys[i], -5]) cylinder(d = i == 1 ? 11 : 8, h = 10);
        translate([cx + 10, ys[0], 2]) dimples(1);
        translate([cx + 10, ys[2], 2]) dimples(2);
        // engraved arrow at the front edge pointing at the muzzle
        translate([cx, w + inner.y - 3, 2 - 0.9]) linear_extrude(2) polygon([[-4, -4], [4, -4], [0, 1]]);
    }
    for (i = [0 : 2]) translate([cx, ys[i], -1.5]) difference() {
        translate([-7.6, -7.6, 0]) cube([15.2, 15.2, 1.5]);
        translate([-6.3, -6.3, -1]) cube([12.6, 12.6, 4]);
    }
}

if (part == "tray") tray_part();
else if (part == "lid") translate([0, 0, 2]) rotate([180, 0, 0]) lid_part();
else { tray_part(); translate([inner.x + 14, 0, 0]) lid_part(); }
