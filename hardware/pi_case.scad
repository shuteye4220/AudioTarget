// Belt case for the Pi, with three menu buttons on the lid:
//   Up (one dimple beside it), Select (big, middle), Down (two dimples).
// Wire them to GPIO5 / GPIO13 / GPIO6 and ground (see docs/wiring.md).
// Bolt the belt loop (part = "loop") to the back with 4 x M3x12 + nuts;
// it takes a belt up to 40 mm wide.
include <lib.scad>

board_type = "zero2w";  // "zero2w" or "pi5" (also fits Pi 3 / Pi 4)
part = "both";          // "tray", "lid", "loop" or "both"

function bd(t) = t == "pi5"
    ? [[85, 56], [[3.5, 3.5], [61.5, 3.5], [3.5, 52.5], [61.5, 52.5]], 24]
    : [[65, 30], [[3.5, 3.5], [61.5, 3.5], [3.5, 26.5], [61.5, 26.5]], 12];

B = bd(board_type);
bsize = B[0]; bholes = B[1]; above = B[2];   // parts height above the board
gap = 2;                                      // board to wall
inner = [bsize.x + 2 * gap, bsize.y + 2 * gap + 14, above + 9];  // +14 room for buttons' wiring
w = 2; f = 2;
standoff = 4;

module tray_part() {
    difference() {
        union() {
            tray(inner, w, f);
            for (h = bholes) translate([w + gap + h.x, w + gap + h.y, f]) post(standoff, 5, 2.2);
            for (x = [w + 3, w + inner.x - 3], y = [w + 3, w + inner.y - 3])
                translate([x, y, f]) post(inner.z - 0.5);
        }
        // side ports (power / HDMI / USB) along the board's long edge
        translate([w + gap + 4, -1, f + standoff - 1]) cube([bsize.x - 8, w + 2, board_type == "pi5" ? 9 : 6]);
        // Pi 5: USB / Ethernet end
        if (board_type == "pi5")
            translate([w + inner.x - 1, w + gap + 2, f + standoff]) cube([w + 2, bsize.y - 4, 17]);
        // cable slot at the far end for the camera / UART cable
        translate([w + inner.x / 2 - 12, w + inner.y - 1, f + standoff + 4]) cube([24, w + 2, 6]);
        // belt-loop screw holes
        for (x = [w + 10, w + inner.x - 10], y = [w + 8, w + inner.y - 8])
            translate([x, y, -1]) cylinder(d = 3.3, h = f + 2);  // M3 bolts + nuts
        // vents
        for (i = [0 : 5]) translate([w + 10 + i * 8, w + inner.y / 2 - 10, -1]) cube([3, 20, f + 2]);
    }
}

module lid_part() {
    cx = w + inner.x / 2;
    ys = [w + inner.y - 14, w + inner.y / 2, w + 14];  // up, select, down
    difference() {
        lid([inner.x, inner.y, inner.z], w, 2);
        for (x = [w + 3, w + inner.x - 3], y = [w + 3, w + inner.y - 3])
            translate([x, y, -5]) cylinder(d = 2.8, h = 10);
        // up / down: 8 mm caps, select: 11 mm
        for (i = [0 : 2]) translate([cx, ys[i], -5]) cylinder(d = i == 1 ? 11 : 8, h = 10);
        // vents off to the side of the buttons
        for (i = [0 : 4]) translate([w + 6, w + 12 + i * 8, -5]) cube([12, 3, 10]);
        // tactile dimples to the right: one by Up, two by Down
        translate([cx + 11, ys[0], 2]) dimples(1);
        translate([cx + 11, ys[2], 2]) dimples(2);
    }
    for (i = [0 : 2]) translate([cx, ys[i], -1.5]) difference() {
        translate([-7.6, -7.6, 0]) cube([15.2, 15.2, 1.5]);
        translate([-6.3, -6.3, -1]) cube([12.6, 12.6, 4]);
    }
}

module loop_part() {
    lw = inner.x + 2 * w; lh = inner.y + 2 * w;
    difference() {
        union() {
            cube([lw, lh, 2.5]);
            // two rails along the top and bottom edges hold the strap 5 mm off the case
            for (y = [0, lh - 8]) translate([0, y, 0]) cube([lw, 8, 8]);
            translate([0, 0, 8]) cube([lw, lh, 2.5]);
        }
        // belt channel (runs across), 42 mm tall
        translate([-1, (lh - 42) / 2, 2.5]) cube([lw + 2, 42, 5.5]);
        for (x = [10, lw - 10], y = [8, lh - 8]) translate([x, y, -1]) {
            cylinder(d = 3.2, h = 20);
            translate([0, 0, 8.5]) cylinder(d = 6, h = 5);
        }
    }
}

if (part == "tray") tray_part();
else if (part == "lid") translate([0, 0, 2]) rotate([180, 0, 0]) lid_part();
else if (part == "loop") loop_part();
else { tray_part(); translate([inner.x + 10, 0, 0]) lid_part(); translate([-inner.x - 14, 0, 0]) loop_part(); }
