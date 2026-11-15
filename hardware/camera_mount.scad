// Camera on a Picatinny rail, lens forward along the barrel.
// The camera board bolts to the FRONT face of the plate on 6 mm spacers
// (M2.5 x 12 screws from behind), leaving room for the ribbon or USB cable.
// Default: Raspberry Pi HQ camera (38 mm board, M2.5 holes on a 30 mm square).
// For a USB camera module, change board/holes to suit.
include <lib.scad>

board   = 38;     // board width/height
holes   = 30;     // mounting-hole square
hole_d  = 2.7;    // M2.5 clearance
axis_h  = 30;     // lens centre height above the rail top
plate_t = 3.5;

difference() {
    union() {
        rail_clamp(len = 36, width = 30, roof = 4, bolt_at = 18);
        // upright plate at the front of the clamp
        translate([-(board + 6) / 2, 36 - plate_t, 1])
            cube([board + 6, plate_t, axis_h + board / 2 + 2]);
        // gussets
        for (x = [-15, 12])   // on the clamp's top, at its edges
            translate([x, 36 - plate_t, 4]) rotate([90, 0, 90])
                linear_extrude(3) polygon([[0, 0], [-28, 0], [0, axis_h - 6]]);
    }
    // board holes
    for (x = [-holes / 2, holes / 2], z = [axis_h - holes / 2, axis_h + holes / 2])
        translate([x, 30, z]) rotate([-90, 0, 0]) cylinder(d = hole_d, h = 20);
}
