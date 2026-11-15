// Gun module box: XIAO nRF52840 Sense, LiPo, two buttons, 3.5 mm jack.
// Slides onto a Picatinny rail; the cross bolt (M4 x 35 + nut) goes through
// a rail slot. Print "tray" upside-down-free as is, "lid" flat side down.
//
// Buttons: 12x12 mm tactile switches glued into the frames under the lid,
// with a round cap on ZERO (toward the muzzle) and a square cap on MODE
// (toward you). Caps must stand at least 2 mm proud of the switch stem.
// Battery switch: a mini slide switch (SS12D00 style) behind the left-wall slot.
include <lib.scad>

part = "both";          // "tray", "lid" or "both"

inner = [32, 56, 16];   // x across the gun, y along the barrel, z height
w = 2; f = 2;
clamp_len = 40;

module tray_part() {
    difference() {
        union() {
            translate([-(inner.x + 2 * w) / 2, 0, 4]) tray(inner, w, f);
            rail_clamp(len = clamp_len, width = 30, roof = 4, bolt_at = 20);
            // lid screw posts
            for (x = [-inner.x / 2 + 3, inner.x / 2 - 3], y = [w + 3, w + inner.y - 3])
                translate([x, y, 4 + f]) post(inner.z - 0.5);
        }
        // USB-C at the rear (toward the shooter), level with the XIAO
        translate([-6.5, -1, 4 + f + 1]) cube([13, w + 2, 7.5]);
        // 3.5 mm jack on the right side, near the rear
        translate([inner.x / 2 + w - 3, 14, 4 + f + 8]) rotate([0, 90, 0]) cylinder(d = 6.6, h = 6);
        // battery slide switch on the left wall, near the rear
        translate([-inner.x / 2 - w - 1, 8, 4 + f + 5]) cube([w + 2, 7, 3.5]);
        // cable gland (wired link to the Pi) at the front
        translate([0, inner.y + w - 3, 4 + f + 9]) rotate([-90, 0, 0]) cylinder(d = 6, h = 6);
    }
    // battery stop rib and XIAO cradle
    translate([-inner.x / 2, w + 24, 4 + f]) cube([inner.x, 1.2, 3]);
}

module lid_part() {
    difference() {
        lid([inner.x, inner.y, inner.z], w, 2);
        // screw holes
        for (x = [w + 3, w + inner.x - 3], y = [w + 3, w + inner.y - 3])
            translate([x, y, -5]) cylinder(d = 2.8, h = 10);
        // ZERO: round cap, toward the muzzle
        translate([w + inner.x / 2, w + inner.y - 16, -5]) cylinder(d = 12.4, h = 10);
        // MODE: square cap, toward the shooter
        translate([w + inner.x / 2 - 6.3, w + 16 - 6.3, -5]) cube([12.6, 12.6, 10]);
        // engraved arrow pointing at the muzzle, so the box can't go on backwards
        translate([w + inner.x / 2, w + inner.y - 4, 2 - 0.9])
            linear_extrude(2) polygon([[-4, -4], [4, -4], [0, 1]]);
        // engraved groove between the buttons
        translate([w + inner.x / 2 - 6, w + inner.y / 2 - 0.9, 2 - 0.9]) cube([12, 1.8, 2]);
    }
    // switch locating frames under the lid
    for (c = [[w + inner.x / 2, w + inner.y - 16], [w + inner.x / 2, w + 16]])
        translate([c.x, c.y, -1.5]) difference() {
            translate([-7.6, -7.6, 0]) cube([15.2, 15.2, 1.5]);
            translate([-6.3, -6.3, -1]) cube([12.6, 12.6, 4]);
        }
}

if (part == "tray") tray_part();
else if (part == "lid") translate([0, 0, 2]) rotate([180, 0, 0]) lid_part();
else { tray_part(); translate([50, 0, 0]) lid_part(); }
