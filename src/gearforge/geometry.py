"""Parametric prototype solids and a portable software-rendered mesh preview.

Gear roots use sampled radial relief, not a generated cutter trochoid. Geometry
is explicitly labeled prototype grade throughout the application and reports.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from functools import lru_cache

from .models import Candidate, GearSpec, PrintProfile, Requirements, candidate_from_dict

COLORS = {"gear": (0.15, 0.78, 0.68), "driven": (0.32, 0.53, 0.94), "shaft": (0.70, 0.74, 0.79),
          "bearing": (0.97, 0.69, 0.32), "housing": (0.24, 0.29, 0.38), "lid": (0.35, 0.41, 0.51), "carrier": (0.75, 0.49, 0.96)}


@lru_cache(maxsize=2048)
def involute_outline(teeth: int, module: float, pressure: float = 20., backlash: float = 0.2,
                     helix: float = 0., internal: bool = False, samples: int = 10):
    alpha_n = math.radians(pressure)
    beta = math.radians(helix)
    mt = module / math.cos(beta)
    alpha = math.atan(math.tan(alpha_n) / math.cos(beta))
    rp = mt * teeth / 2
    rb = rp * math.cos(alpha)
    rmin = rp - (module if internal else 1.25 * module)
    rmax = rp + (1.25 * module if internal else module)
    inv_pitch = math.tan(alpha) - alpha
    h_pitch = math.pi / (2 * teeth) + (backlash if internal else -backlash) / (4 * rp)

    def half(r):
        t = math.acos(min(1., rb / r))
        return h_pitch + inv_pitch - (math.tan(t) - t)

    if half(rmax) <= 0 or rmin <= 0:
        raise ValueError("Tooth tip is pointed or root radius is invalid; reduce backlash or increase tooth size")
    flank_start = max(rmin, rb)
    points = []

    def append(r, a):
        p = (r * math.cos(a), r * math.sin(a))
        if not points or math.dist(points[-1], p) > 1e-8:
            points.append(p)

    for tooth in range(teeth):
        center = 2 * math.pi * tooth / teeth
        hroot = half(flank_start)
        append(rmin, center - hroot)
        if flank_start > rmin:
            append(flank_start, center - hroot)
        for i in range(samples+1):
            r = flank_start + (rmax-flank_start) * i / samples
            append(r, center-half(r))
        htip = half(rmax)
        for i in range(1, 5):
            append(rmax, center-htip + 2 * htip * i / 4)
        for i in range(samples, -1, -1):
            r = flank_start + (rmax-flank_start) * i / samples
            append(r, center+half(r))
        append(rmin, center+hroot)
        next_left = center + 2 * math.pi / teeth - hroot
        for i in range(1, 5):
            append(rmin, center+hroot + (next_left-center-hroot) * i / 4)
    if math.dist(points[-1], points[0]) < 1e-8:
        points.pop()
    return tuple(points)


@dataclass
class Part:
    name: str
    shape: object
    source: str
    color: tuple
    center: tuple = (0., 0., 0.)
    shaft: int = -1
    print_orientation: str = "Flat base on build plate"


def gear_solid(spec: GearSpec, profile: PrintProfile):
    import cadquery as cq
    backlash = profile.backlash_mm if spec.source == "print" else 0.1
    outline = involute_outline(spec.teeth, spec.module_mm, spec.pressure_deg, backlash, spec.helix_deg, spec.internal)
    wp = cq.Workplane("XY").polyline(outline).close()
    twist = math.degrees(spec.width_mm * math.tan(math.radians(spec.helix_deg)) / (spec.pitch_mm / 2))
    teeth = wp.twistExtrude(spec.width_mm, twist) if abs(twist) > 1e-6 else wp.extrude(spec.width_mm)
    if spec.internal:
        return cq.Workplane("XY").circle(spec.outer_mm/2).extrude(spec.width_mm).cut(teeth)
    body = teeth
    if spec.hub_width_mm:
        hub = cq.Workplane("XY").circle(spec.hub_diameter_mm/2).extrude(spec.hub_width_mm).translate((0, 0, spec.width_mm))
        body = body.union(hub)
    bore = spec.bore_mm + (profile.bore_compensation_mm if spec.source == "print" else 0)
    if bore > spec.pitch_mm - 2.5 * spec.module_mm - 2:
        raise ValueError("Bore leaves insufficient tooth-root material")
    cutter = cq.Workplane("XY").circle(bore/2).extrude(spec.length_mm+2).translate((0, 0, -1))
    body = body.cut(cutter)
    if spec.source == "print" and spec.hub_width_mm >= 5:
        # Cross-drill for a steel torque-transmitting pin. Axis in X at hub midpoint.
        pin = cq.Workplane("YZ").circle(1.5).extrude(spec.hub_diameter_mm + 2, both=True).translate((0, 0, spec.width_mm + spec.hub_width_mm/2))
        body = body.cut(pin)
    # Global shrink correction would change center distances; compensation is applied
    # only to exported print-local parts, never to assembled reference geometry.
    return body


def _bearing_solid(bearing):
    import cadquery as cq
    return cq.Workplane("XY").circle(bearing["outer"]/2).circle(bearing["bore"]/2).extrude(bearing["width"])


def build_parts(c: Candidate, req: Requirements, profile: PrintProfile) -> list[Part]:
    import cadquery as cq
    if c.export_level == "concept":
        raise ValueError(f"{c.family.title()} is concept-only in this release. Export its report and layout instead of manufacturing solids.")
    parts = []
    for item in c.layout:
        s = c.stages[item["stage"]]
        gear = s.planet if item["role"] == "planet" else (s.driver if item["role"] == "driver" else s.driven)
        local = gear_solid(gear, profile)
        if item["name"] == "ring":
            bolt_radius = gear.pitch_mm/2 + 2.7 * gear.module_mm
            for i in range(3):
                angle = math.radians(30+i*120-item["rotation_deg"])
                drill = cq.Workplane("XY").center(bolt_radius*math.cos(angle),bolt_radius*math.sin(angle)).circle(1.1).extrude(gear.width_mm)
                local = local.cut(drill)
        shape = local.rotate((0, 0, 0), (0, 0, 1), item["rotation_deg"]).translate((item["x"], item["y"], item["z"]))
        color = COLORS["driven"] if item["role"] == "driven" else COLORS["gear"]
        parts.append(Part(item["name"], shape, gear.source, color, (item["x"], item["y"], item["z"]), item["shaft"], profile.orientation))
    sx, sy, sz = c.size_mm
    flange, wall, bottom = 6., 5., 14.
    if c.family == "planetary":
        s = c.stages[0]
        center = sx/2
        carrier_z = 21 + s.driver.length_mm + 3
        carrier_radius = s.center_mm + 8
        carrier = cq.Workplane("XY").circle(carrier_radius).extrude(6)
        # Sun shaft ends before carrier. Output shaft engages carrier through cross pin.
        outshaft = c.shafts[1]
        hub = cq.Workplane("XY").circle(outshaft["diameter"]/2+6).extrude(10).translate((0, 0, 6))
        carrier = carrier.union(hub).cut(cq.Workplane("XY").circle((outshaft["diameter"]+profile.bore_compensation_mm)/2).extrude(18))
        cross = cq.Workplane("YZ").circle(1.5).extrude(40, both=True).translate((0, 0, 11))
        carrier = carrier.cut(cross)
        for item in c.layout:
            if item["role"] == "planet":
                x, y = item["x"]-center, item["y"]-center
                carrier = carrier.cut(cq.Workplane("XY").center(x, y).circle(4.075).extrude(10))
                pin = cq.Workplane("XY").circle(4).extrude(s.planet.width_mm+s.driver.hub_width_mm+12).translate((item["x"], item["y"], 18))
                parts.append(Part(item["name"]+"_pin", pin, "purchase", COLORS["shaft"], (item["x"], item["y"], 18)))
        parts.append(Part("carrier", carrier.translate((center, center, carrier_z)), "print", COLORS["carrier"], (center, center, carrier_z), 1))
    for shaft in c.shafts:
        b = shaft["bearing"]
        if c.family == "planetary":
            if shaft["index"] == 0:
                zstart, zend, bz = -12., 21 + c.stages[0].driver.length_mm - 1, 3.
            else:
                zstart, zend, bz = 24+c.stages[0].driver.length_mm, sz+12, sz-10
            bearing_zs = [bz]
        else:
            zstart, zend = -12., sz+12.
            bearing_zs = [3., sz-10.]
        local = cq.Workplane("XY").circle(shaft["diameter"]/2).extrude(zend-zstart)
        # Cut corresponding torque-transmitting pin bores in printed-gear shafts.
        for item in c.layout:
            if item["shaft"] == shaft["index"]:
                s = c.stages[item["stage"]]
                gear = s.driver if item["role"] == "driver" else s.driven
                if gear.source == "print" and gear.hub_width_mm:
                    zp = item["z"] + gear.width_mm + gear.hub_width_mm/2 - zstart
                    cut = cq.Workplane("YZ").circle(1.5).extrude(shaft["diameter"]+2, both=True).translate((0, 0, zp))
                    cut = cut.rotate((0, 0, 0), (0, 0, 1), item["rotation_deg"])
                    local = local.cut(cut)
        if c.family == "planetary" and shaft["index"] == 1:
            zp = 21+c.stages[0].driver.length_mm+3+11-zstart
            local = local.cut(cq.Workplane("YZ").circle(1.5).extrude(shaft["diameter"]+2, both=True).translate((0, 0, zp)))
        shape = local.translate((shaft["x"], shaft["y"], zstart))
        parts.append(Part(f"shaft_{shaft['index']+1}", shape, "machine", COLORS["shaft"], (shaft["x"], shaft["y"], zstart), shaft["index"]))
        for i, z in enumerate(bearing_zs):
            shape = _bearing_solid(b).translate((shaft["x"], shaft["y"], z))
            parts.append(Part(f"bearing_{shaft['index']+1}_{i+1}", shape, "purchase", COLORS["bearing"], (shaft["x"], shaft["y"], z)))
    # Split box with a base flange, bearing pockets and a removable lid.
    outer = cq.Workplane("XY").box(sx-2*flange, sy-2*flange, sz-10, centered=(False, False, False)).translate((flange, flange, 0))
    outer = outer.union(cq.Workplane("XY").box(sx, sy, 5, centered=(False, False, False)))
    cavity = cq.Workplane("XY").box(sx-2*(flange+wall), sy-2*(flange+wall), sz, centered=(False, False, False)).translate((flange+wall, flange+wall, bottom))
    housing = outer.cut(cavity)
    if c.family == "planetary":
        ring = c.stages[0].driven
        bolt_radius = ring.pitch_mm/2 + 2.7*ring.module_mm
        for i in range(3):
            angle = math.radians(30+i*120)
            x,y = sx/2+bolt_radius*math.cos(angle),sy/2+bolt_radius*math.sin(angle)
            post = cq.Workplane("XY").center(x,y).circle(2.3).extrude(21)
            housing = housing.union(post)
            drill = cq.Workplane("XY").center(x,y).circle(1.1).extrude(22)
            housing = housing.cut(drill)
    lid = cq.Workplane("XY").box(sx, sy, 10, centered=(False, False, False)).translate((0, 0, sz-10))
    # Retained bottom and upper bearing pockets with 3 mm axial shoulders.
    for shaft in c.shafts:
        b, x, y = shaft["bearing"], shaft["x"], shaft["y"]
        clearance = profile.bearing_clearance_mm if req.mode != "commercial" else 0.02
        if c.family != "planetary" or shaft["index"] == 0:
            pocket = cq.Workplane("XY").center(x, y).circle((b["outer"]+clearance)/2).extrude(b["width"]+0.1).translate((0, 0, 3))
            housing = housing.cut(pocket)
            passage = cq.Workplane("XY").center(x, y).circle((shaft["diameter"]+0.5)/2).extrude(bottom+1)
            housing = housing.cut(passage)
        if c.family != "planetary" or shaft["index"] == 1:
            pocket = cq.Workplane("XY").center(x, y).circle((b["outer"]+clearance)/2).extrude(b["width"]+0.1).translate((0, 0, sz-10))
            lid = lid.cut(pocket)
            passage = cq.Workplane("XY").center(x, y).circle((shaft["diameter"]+0.5)/2).extrude(12).translate((0, 0, sz-10))
            lid = lid.cut(passage)
    bolts = [(6., 6.), (sx-6, 6.), (6., sy-6), (sx-6, sy-6)]
    for x, y in bolts:
        drill = cq.Workplane("XY").center(x, y).circle(2.2).extrude(sz+2).translate((0, 0, -1))
        housing, lid = housing.cut(drill), lid.cut(drill)
        # Nut captures open from the bottom for through bolts.
        nut = cq.Workplane("XY").center(x, y).polygon(6, 8.3).extrude(3)
        housing = housing.cut(nut)
    if req.mounting == "foot":
        for x, y in [(sx/3, 5.5), (2*sx/3, 5.5), (sx/3, sy-5.5), (2*sx/3, sy-5.5)]:
            housing = housing.cut(cq.Workplane("XY").center(x, y).circle(2.75).extrude(bottom+1))
    else:
        # Same envelope, flange mounting through side ears; geometry is explicit.
        for x, y in [(5.5, sy/3), (5.5, 2*sy/3), (sx-5.5, sy/3), (sx-5.5, 2*sy/3)]:
            housing = housing.cut(cq.Workplane("XY").center(x, y).circle(2.75).extrude(bottom+1))
    source = "print" if req.mode != "commercial" else "machine"
    parts.append(Part("housing", housing, source, COLORS["housing"], (0, 0, 0)))
    parts.append(Part("lid", lid, source, COLORS["lid"], (0, 0, sz-10)))
    for part in parts:
        shape = part.shape.val()
        if not shape.isValid() or not shape.Solids() or shape.Volume() <= 0:
            raise ValueError(f"CAD generation produced an invalid solid: {part.name}")
    return parts


def mesh_parts(parts: list[Part], tolerance=0.5) -> list[dict]:
    meshes = []
    for part in parts:
        vertices, triangles = part.shape.val().tessellate(tolerance, 0.25)
        meshes.append({"name": part.name, "vertices": [v.toTuple() for v in vertices], "triangles": triangles,
                       "color": part.color, "center": part.center, "shaft": part.shaft, "source": part.source})
    return meshes


def build_preview(candidate: dict, requirements: dict, profile: dict) -> dict:
    c = candidate_from_dict(candidate)
    req, p = Requirements(**requirements), PrintProfile(**profile)
    return {"candidate_id": c.id, "meshes": mesh_parts(build_parts(c, req, p)), "size_mm": c.size_mm}


def collision_report(parts: list[Part], min_volume_mm3=0.05):
    """Broad-phase bounding-box + exact solid intersections.

Contact with bearings/shafts and ring mounting is expected and labeled separately.
CAD checks are static only; full-cycle tooth contact remains unvalidated.
"""
    result = []
    for i, a in enumerate(parts):
        ba = a.shape.val().BoundingBox()
        for b in parts[i+1:]:
            bb = b.shape.val().BoundingBox()
            if ba.xmax <= bb.xmin or bb.xmax <= ba.xmin or ba.ymax <= bb.ymin or bb.ymax <= ba.ymin or ba.zmax <= bb.zmin or bb.zmax <= ba.zmin:
                continue
            overlap = a.shape.val().intersect(b.shape.val()).Volume()
            if overlap > min_volume_mm3:
                expected = (a.name.startswith("shaft_") or b.name.startswith("shaft_") or "bearing" in a.name or "bearing" in b.name)
                result.append({"a": a.name, "b": b.name, "overlap_mm3": round(overlap, 4), "status": "review-fit" if expected else "interference"})
    return result
