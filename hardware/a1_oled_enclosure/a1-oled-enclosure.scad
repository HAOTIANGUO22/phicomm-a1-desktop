// A1 local controller enclosure. All dimensions are in millimeters.
// Set part to "base", "lid", "fit", "oled_fit", "assembly", or "exploded".
// X increases toward the USB-C/DC connectors; Y increases toward the DC jack.
part = "assembly"; // [assembly, exploded, base, lid, fit, oled_fit]

/* [Case] */
with_oled = true;        // Set false for a solid lid without the OLED module.
case_length = 84;
case_width = 73;
base_height = 33;        // Original M3 base: do not change or reprint it.
lid_rise = 5;            // Extra clearance is entirely in the replacement lid.
wall = 2.4;
floor_thickness = 4.0;
lid_thickness = 2.8;
lid_inner_z = lid_thickness + lid_rise;
corner_radius = 5;
lid_gap = 0.38;          // Radial clearance on each side of the locating lip.
lip_height = 2.4;
lip_width = 1.5;

/* [Main board: supplied reference drawing and photos] */
pcb_origin = [9.4, 9.2];
pcb_size = [68.58, 53.34]; // 66.04 mm body plus the 2.54 mm edge detail.
pcb_spacing = 4;         // Use 4 mm insulating spacers underneath the PCB.
pcb_thickness = 1.6;
pcb_mounts = [[2.65, 46.0], [54.61, 50.8], [2.65, 18.06], [53.2, 2.54]];
pcb_mount_angles = [0, 90, 90, 0];
mount_slot_length = 10.0;
mount_slot_width = 3.6;   // M3 clearance through the printed floor.
screw_head_recess = 2.2; // For a low button-head M3 screw and thin washer.
recess_length = 15.2;
recess_width = 9.2;

/* [Right-side connectors and lid controls] */
usb_y = 13.4;            // Relative to the PCB's front edge.
usb_width = 20;
usb_bottom = 5.4;        // Relative to the enclosure bottom.
usb_top = 15.6;          // Full-width region. The 45 degree roof extends higher.
dc_y = 48.0;
dc_width = 17.8;
dc_bottom = 5.4;
dc_top = 20.0;
port_roof = 3.6;
reset_xy = [62.7, 3.8];  // Relative to the PCB origin.
reset_opening = [11, 7.2];

/* [IR receiver under lid] */
ir_center = [25, 56.5];
ir_window = [15, 12];
ir_hole_x = 7.8;         // From lens center toward the two PCB mounting holes.
ir_hole_pitch = 11.6;
ir_support_height = 8.1; // +4 mm: clearance for the existing right-angle header and Dupont plug.
ir_slot_width = 1.7;     // Pilot for M2 screws; adjust for your filament.
ir_slot_length = 5.5;

/* [0.96-inch four-pin OLED: nominal module, confirm using the fit coupon] */
oled_center = [36,27.5];
oled_pcb = [27.3,27.8];
oled_pitch = [23.3,23.8];
oled_window = [25.6,17.6];
oled_standoff = 3.1;    // PCB mounting height and all hole centers remain unchanged.
oled_glass_pocket = [27.2,19.6]; // Back-side relief; front viewing window stays unchanged.
oled_pocket_depth = 1.0; // Relieves the roughly 0.5 mm glass seating shortfall.
oled_pilot = 1.7;      // M2 screws, not the M3 main-board fasteners.
oled_points = [for(x=[-1,1],y=[-1,1])
    oled_center+[x*oled_pitch.x/2,y*oled_pitch.y/2]];

/* [Lid screws] */
corner_inset = 5;
lid_screw_clearance = 3.35;
base_pilot = 2.65;
screw_boss_diameter = 7.8;
pilot_depth = 8;
engrave_labels = true;
$fn = 48;
eps = 0.03;

screw_points = [[corner_inset,corner_inset],
                [case_length-corner_inset,corner_inset],
                [corner_inset,case_width-corner_inset],
                [case_length-corner_inset,case_width-corner_inset]];
pcb_points = [for (p = pcb_mounts) pcb_origin+p];
pcb_top = floor_thickness+pcb_spacing+pcb_thickness;

assert(case_length > pcb_origin.x + pcb_size.x + wall);
assert(case_width > pcb_origin.y + pcb_size.y + wall);
assert(base_height > floor_thickness + pcb_spacing + pcb_thickness + 17);
assert(wall + lid_gap < corner_radius);

module rounded_rect(size, radius) {
    r = min(radius,min(size.x,size.y)/2-0.01);
    hull() for (x = [r,size.x-r], y = [r,size.y-r])
        translate([x,y]) circle(r=r);
}

module outline(inset=0) {
    translate([inset,inset])
        rounded_rect([case_length-2*inset,case_width-2*inset],max(0.35,corner_radius-inset));
}

module centered_rounded(size,radius) {
    translate([-size.x/2,-size.y/2]) rounded_rect(size,radius);
}

module slot(length,width) {
    hull() for (x=[-(length-width)/2,(length-width)/2])
        translate([x,0]) circle(d=width);
}

// Shape in the Y/Z plane, cut through the right wall along X.
module port(center_y,width,low,high,rise) {
    translate([case_length-wall-2,center_y,0])
        multmatrix([[0,0,1,0],[1,0,0,0],[0,1,0,0],[0,0,0,1]])
            linear_extrude(height=wall+4)
                polygon([[-width/2+1,low],[width/2-1,low],
                         [width/2,low+1],[width/2,high],
                         [width/2-rise,high+rise],[-width/2+rise,high+rise],
                         [-width/2,high],[-width/2,low+1]]);
}

module board_fastener_cuts() {
    for (i=[0:len(pcb_points)-1]) {
        translate([pcb_points[i].x,pcb_points[i].y,-eps])
            rotate([0,0,pcb_mount_angles[i]]) {
                linear_extrude(height=floor_thickness+2*eps)
                    slot(mount_slot_length,mount_slot_width);
                linear_extrude(height=screw_head_recess+eps)
                    slot(recess_length,recess_width);
            }
    }
}

module side_vents() {
    // Narrow holes have a short roof and leave the antenna-side wall solid plastic.
    for (x=[20:7:62])
        translate([x,case_width-wall-1,21])
            rotate([-90,0,0])
                linear_extrude(height=wall+2)
                    centered_rounded([3.2,8],1.55);
}

module base() {
    difference() {
        union() {
            difference() {
                linear_extrude(height=base_height) outline();
                translate([0,0,floor_thickness])
                    linear_extrude(height=base_height-floor_thickness+eps) outline(wall);
            }
            for (p=screw_points)
                translate([p.x,p.y,floor_thickness-eps])
                    cylinder(d=screw_boss_diameter,h=base_height-floor_thickness+eps);
        }
        for (p=screw_points)
            translate([p.x,p.y,base_height-pilot_depth])
                cylinder(d=base_pilot,h=pilot_depth+eps);
        board_fastener_cuts();
        port(pcb_origin.y+usb_y,usb_width,usb_bottom,usb_top,port_roof);
        port(pcb_origin.y+dc_y,dc_width,dc_bottom,dc_top,port_roof);
        side_vents();
    }
}

module rim() {
    i = wall+lid_gap;
    difference() {
        linear_extrude(height=lip_height+eps) outline(i);
        translate([0,0,-eps]) linear_extrude(height=lip_height+3*eps) outline(i+lip_width);
        // Clear the four base pillars so they can touch the flat back of the lid.
        for (p=screw_points)
            translate([p.x,p.y,-eps])
                cylinder(d=screw_boss_diameter+2*lid_gap+0.6,h=lip_height+3*eps);
    }
}

module ir_opening() {
    // First printed layer is the visible outside face. Flare the opening toward it.
    translate([ir_center.x,ir_center.y,0]) {
        hull() {
            translate([0,0,-eps]) linear_extrude(height=eps)
                centered_rounded(ir_window+[2.4,2.4],2.8);
            translate([0,0,1.2]) linear_extrude(height=eps)
                centered_rounded(ir_window,1.6);
        }
        translate([0,0,1.2-eps])
            linear_extrude(height=lid_thickness-1.2+2*eps)
                centered_rounded(ir_window,1.6);
    }
}

module lid_vents() {
    for (y=[31:4.5:54])
        translate([65,y,-eps])
            linear_extrude(height=lid_thickness+2*eps)
                centered_rounded([12,2.2],1.06);
}

module oled_opening() {
    translate([oled_center.x,oled_center.y,0]) {
        hull() {
            translate([0,0,-eps]) linear_extrude(height=eps)
                centered_rounded(oled_window+[1.4,1.4],1.6);
            translate([0,0,0.8]) linear_extrude(height=eps)
                centered_rounded(oled_window,0.9);
        }
        translate([0,0,0.8-eps]) linear_extrude(height=lid_thickness+eps)
            centered_rounded(oled_window,0.9);
    }
}

// Clear the glass behind the bezel and trim the inner edges of the posts.
// This is a back-side pocket, not a larger visible opening through the front.
module oled_glass_relief() {
    translate([oled_center.x,oled_center.y,lid_thickness-oled_pocket_depth])
        linear_extrude(height=oled_pocket_depth+oled_standoff+2*eps)
            centered_rounded(oled_glass_pocket,0.4);
}

// Local cable passage in the left locating lip; the outer skirt is unchanged.
module ir_wire_relief() {
    translate([wall,ir_center.y-5,lid_inner_z-1.2])
        cube([lid_gap+lip_width+1.0,10,lip_height+1.2+2*eps]);
}

module oled_supports() {
    for(p=oled_points)
        translate([p.x,p.y,lid_thickness-eps])
            rotate([0,0,90]) linear_extrude(height=oled_standoff+eps)
                slot(5.6,4.4);
}

module oled_fasteners() {
    for(p=oled_points)
        translate([p.x,p.y,lid_thickness-0.8])
            rotate([0,0,90]) linear_extrude(height=oled_standoff+0.8+eps)
                slot(3.0,oled_pilot);
}

module engraving(label, position, size) {
    translate([position.x,position.y,-eps])
        linear_extrude(height=0.48+eps)
            text(label,size=size,font="Arial:style=Bold",halign="center",valign="center");
}

module lid_shape() {
    p = pcb_origin+reset_xy;
    ir_x = ir_center.x+ir_hole_x;
    difference() {
        union() {
            linear_extrude(height=lid_thickness) outline();
            // A hollow 5 mm skirt makes this a raised lid on the unchanged base.
            translate([0,0,lid_thickness-eps]) difference() {
                linear_extrude(height=lid_rise+eps) outline();
                translate([0,0,-eps]) linear_extrude(height=lid_rise+3*eps) outline(wall);
            }
            for(q=screw_points)
                translate([q.x,q.y,lid_thickness-eps])
                    cylinder(d=screw_boss_diameter,h=lid_rise+eps);
            // Join the inset locating lip to the skirt with an inward slope.
            // Without this bridge the lip would become four detached segments.
            translate([0,0,lid_inner_z-2]) difference() {
                linear_extrude(height=2) outline();
                hull() {
                    translate([0,0,-eps]) linear_extrude(height=eps) outline(wall);
                    translate([0,0,2+eps]) linear_extrude(height=eps)
                        outline(wall+lid_gap+lip_width);
                }
            }
            translate([0,0,lid_inner_z-eps]) rim();
            translate([ir_x,ir_center.y,lid_thickness-eps])
                linear_extrude(height=ir_support_height+eps)
                    centered_rounded([5.4,22],1.7);
            if (with_oled) oled_supports();
        }
        for (q=screw_points) {
            translate([q.x,q.y,-eps]) cylinder(d=lid_screw_clearance,h=lid_inner_z+lip_height+2*eps);
            // A shallow relief for the head of a button-head M3 screw.
            translate([q.x,q.y,-eps]) cylinder(d1=6.4,d2=lid_screw_clearance,h=1.4);
        }
        ir_opening();
        if (with_oled) {
            oled_opening();
            oled_glass_relief();
            oled_fasteners();
        }
        ir_wire_relief();
        for (dy=[-ir_hole_pitch/2,ir_hole_pitch/2])
            translate([ir_x,ir_center.y+dy,lid_thickness+0.2])
                rotate([0,0,90])
                    linear_extrude(height=ir_support_height+eps)
                        slot(ir_slot_length,ir_slot_width);
        translate([p.x,p.y,-eps]) linear_extrude(height=lid_thickness+2*eps)
            centered_rounded(reset_opening,1.7);
        lid_vents();
        if (engrave_labels) {
            engraving(with_oled ? "A1 OLED 3.0" : "A1",[32,9],3.2);
            engraving("RESET",[p.x,p.y+7.0],2.7);
        }
    }
}

// Print with the outer face down. Mirror Y here so a real 180-degree X
// rotation during assembly puts RESET and all lettering in the intended XY.
module lid() {
    translate([0,case_width,0]) mirror([0,1,0]) lid_shape();
}

module oled_fit_fixture() {
    translate([0,36.5,0]) mirror([0,1,0]) translate([-15,-8,0]) intersection() {
        lid_shape();
        translate([15,8,-eps]) cube([42,36.5,lid_thickness+oled_standoff+2*eps]);
    }
}

module fit_fixture() {
    // Prints quickly: a low perimeter, four actual fastener zones, and the USB wall.
    intersection() {
        base();
        union() {
            difference() {
                linear_extrude(height=5.0) outline();
                translate([0,0,-eps]) linear_extrude(height=5.0+2*eps) outline(5.0);
            }
            for (i=[0:len(pcb_points)-1]) {
                p=pcb_points[i];
                anchor = i==0 || i==2 ? [3,p.y] :
                         i==1 ? [p.x,case_width-3] : [p.x,3];
                linear_extrude(height=floor_thickness+eps)
                    hull() {
                        translate(p) circle(r=8.8);
                        translate(anchor) circle(r=3.4);
                    }
            }
            translate([case_length-wall-0.2,pcb_origin.y+usb_y-usb_width/2-2,0])
                cube([wall+0.2,usb_width+4,usb_top+port_roof+2]);
        }
    }
}

module installed_lid(lift=0) {
    // Physical assembly uses rotation, never a reflection of the printed part.
    translate([0,case_width,base_height+lid_inner_z+lift]) rotate([180,0,0]) lid();
}

module demo_hardware() {
    color("#2C403A") translate([pcb_origin.x,pcb_origin.y,floor_thickness+pcb_spacing])
        linear_extrude(height=pcb_thickness)
            polygon([[2.6,0],[pcb_size.x,0],[pcb_size.x,pcb_size.y-1.2],
                     [pcb_size.x-1.5,pcb_size.y],[4.5,pcb_size.y],[1,49],[0,46],
                     [0,16],[2.6,13]]);
    color("#D9A441") translate([pcb_origin.x+2.8,pcb_origin.y+1.2,pcb_top]) cube([49,3.4,8.0]);
    color("#D2B05A") translate([pcb_origin.x+5,pcb_origin.y+49,pcb_top]) cube([45,3.2,8.2]);
    color("#92A7AF") translate([pcb_origin.x+8,pcb_origin.y+22,pcb_top]) cube([18,18,3.1]);
    color("#BBCDD2") translate([pcb_origin.x+63.5,pcb_origin.y+usb_y-4.4,pcb_top]) cube([6.8,8.8,3.4]);
    color("#333C41") translate([pcb_origin.x+59,pcb_origin.y+dc_y-4.7,pcb_top]) cube([14,9.4,9.2]);
}

module ir_demo(lift=0) {
    front=base_height+lid_rise-ir_support_height+lift;
    color("#293C35") translate([ir_center.x-10,ir_center.y-7.5,front-1.6]) cube([20,15,1.6]);
    color("#87999B") translate([ir_center.x-3.8,ir_center.y-3.8,front]) cube([7.6,7.6,2.1]);
    color("#182A32") translate([ir_center.x,ir_center.y,front+3.2]) sphere(d=6);
}

module oled_demo(lift=0) {
    z=base_height+lid_inner_z+lift;
    color("#174D8A") translate([oled_center.x-oled_pcb.x/2,oled_center.y-oled_pcb.y/2,
                               z-lid_thickness-oled_standoff-1.2])
        cube([oled_pcb.x,oled_pcb.y,1.2]);
    color("#142028") translate([oled_center.x-13.0,oled_center.y-9.3,z-3.5]) cube([26,18.6,0.8]);
    color("#FFE27B") translate([oled_center.x-10.87,oled_center.y+2.72,z-2.68]) cube([21.74,2.72,0.04]);
    color("#73C5FF") translate([oled_center.x-10.87,oled_center.y-5.43,z-2.68]) cube([21.74,8.15,0.04]);
    // Approximate 4-pin connection edge faces the rear of the enclosure.
    color("#BC9F46") translate([oled_center.x-5,oled_center.y+11.3,z-10.0]) cube([10,1.5,5]);
}

if (part=="base") base();
else if (part=="lid") lid();
else if (part=="fit") fit_fixture();
else if (part=="oled_fit") oled_fit_fixture();
else if (part=="assembly") {
    color("#D9E3DD") base();
    color("#3C7772") installed_lid();
    if (with_oled) oled_demo();
    ir_demo();
}
else if (part=="exploded") {
    color("#D9E3DD") base();
    color("#3C7772") installed_lid(22);
    demo_hardware();
    if (with_oled) oled_demo(22);
    ir_demo(22);
}
else assert(false,str("Unknown part: ",part));
