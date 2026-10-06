"""Deterministic synthesis and explicitly preliminary engineering calculations.

The engine never promotes a screening pass to a validated service rating.
No trained model, executable project data, or network access is required.
"""
from __future__ import annotations

import copy
import hashlib
import itertools
import json
import math
import time
from collections import Counter
from dataclasses import asdict

from .catalog import BEARINGS, Catalog
from .models import Candidate, Check, GearSpec, MODULES, PrintProfile, Requirements, SearchResult, Stage


def external_contact_ratio(a: GearSpec, b: GearSpec) -> float:
    alpha = math.radians(a.pressure_deg)
    ra, rb = a.pitch_mm / 2, b.pitch_mm / 2
    basea, baseb = ra * math.cos(alpha), rb * math.cos(alpha)
    path = math.sqrt((ra + a.module_mm) ** 2 - basea ** 2) + math.sqrt((rb + b.module_mm) ** 2 - baseb ** 2)
    path -= (ra + rb) * math.sin(alpha)
    transverse = path / (math.pi * a.module_mm / math.cos(math.radians(a.helix_deg)) * math.cos(alpha))
    overlap = min(a.width_mm, b.width_mm) * abs(math.sin(math.radians(a.helix_deg))) / (math.pi * a.module_mm)
    return transverse + overlap


def _pair(a, b, family):
    if abs(a.module_mm - b.module_mm) > 1e-6 or abs(a.pressure_deg - b.pressure_deg) > 1e-6:
        return None
    if family == "helical" and abs(a.helix_deg + b.helix_deg) > 1e-6:
        return None
    if a.teeth >= b.teeth:
        return None
    efficiency = (0.96 if family == "helical" else 0.95) if a.source == b.source == "catalog" else (0.91 if family == "helical" else 0.90)
    return Stage(copy.deepcopy(a), copy.deepcopy(b), b.teeth / a.teeth, efficiency, (a.pitch_mm + b.pitch_mm) / 2)


def _parallel_sets(req, profile, catalog):
    tooth_counts = (18, 20, 24, 28, 30, 32, 36, 40, 48, 50, 60, 64, 72, 80, 90, 96, 100)
    for family in (f for f in req.families if f in ("spur", "helical", "bevel")):
        if family == "bevel":
            # Involute cones require spherical tooth geometry. This release searches
            # packaging concepts and exports a labeled layout, never fake tooth solids.
            if req.mode == "commercial":
                continue
        stock = catalog.gears(req.supplier, family, req.currency) if req.mode != "printed" else []
        for module in MODULES:
            if not req.min_module_mm <= module <= req.max_module_mm:
                continue
            for width in (8., 12., 18., 24.):
                gears = []
                if req.mode != "commercial":
                    for teeth in tooth_counts:
                        helix = 20. if family == "helical" else 0.
                        gears.append(GearSpec(teeth, module, width, 8., helix_deg=helix, material=profile.material))
                gears += [g for g in stock if g.module_mm == module]
                if len(gears) > 400:
                    raise ValueError("More than 400 compatible source variants for one module. Narrow the supplier filter or import a smaller working catalog.")
                pairs = []
                for a, b in itertools.product(gears, gears):
                    if family == "helical" and a.source == b.source == "print":
                        b = copy.deepcopy(b)
                        b.helix_deg = -a.helix_deg
                    stage = _pair(a, b, family)
                    if stage and stage.ratio <= 6:
                        pairs.append(stage)
                tolerance = req.ratio_tolerance_percent / 100
                for p in pairs:
                    if abs(p.ratio / req.ratio - 1) <= tolerance:
                        yield family, [p], "concept" if family == "bevel" else "prototype"
                if req.max_stages == 2 and family != "bevel":
                    # Search by ratio buckets rather than taking every Cartesian pair.
                    grouped = {}
                    for p in pairs:
                        grouped.setdefault(round(p.ratio, 8), []).append(p)
                    for r1, choices in sorted(grouped.items()):
                        r2 = req.ratio / r1
                        matching = [rr for rr in grouped if abs(rr / r2 - 1) <= tolerance]
                        for rr in matching:
                            for first in choices[:8]:
                                for second in grouped[rr][:8]:
                                    yield family, [first, second], "prototype"


def _planetary_sets(req, profile, catalog):
    if "planetary" not in req.families or req.mode == "commercial":
        return
    for module in MODULES:
        if not req.min_module_mm <= module <= req.max_module_mm:
            continue
        for width in (10., 16., 24.):
            for sun in range(18, 43, 2):
                for planet in range(18, 51, 2):
                    ring = sun + 2 * planet
                    ratio = 1 + ring / sun
                    if abs(ratio / req.ratio - 1) > req.ratio_tolerance_percent / 100:
                        continue
                    if (sun + ring) % 3:
                        continue
                    radius = module * (sun + planet) / 2
                    if math.sqrt(3) * radius <= module * (planet + 2) + 1:
                        continue
                    a = GearSpec(sun, module, width, req.input_shaft_mm, material=profile.material)
                    b = GearSpec(ring, module, width, 0, material=profile.material, internal=True)
                    p = GearSpec(planet, module, width, 8, material=profile.material)
                    yield "planetary", [Stage(a, b, ratio, 0.85, radius, planet=p, planet_count=3)], "prototype"


def _concept_sets(req, profile):
    for family in (f for f in req.families if f in ("worm", "cycloidal")):
        if req.mode == "commercial":
            continue
        for module in MODULES:
            if not req.min_module_mm <= module <= req.max_module_mm:
                continue
            if family == "worm":
                for starts in (1, 2, 4):
                    wheel = round(req.ratio * starts)
                    if not 18 <= wheel <= 120:
                        continue
                    lead = math.atan(starts / 10)
                    friction_angle = math.atan(0.12 / math.cos(math.radians(20)))
                    efficiency = math.tan(lead) / math.tan(lead + friction_angle)
                    a = GearSpec(starts, module, 10 * module, req.input_shaft_mm, material=profile.material)
                    b = GearSpec(wheel, module, 12 * module, req.output_shaft_mm, material=profile.material)
                    yield family, [Stage(a, b, wheel / starts, efficiency, module * (10 + wheel) / 2)], "concept"
            else:
                lobes = round(req.ratio)
                if not 6 <= lobes <= 60:
                    continue
                a = GearSpec(lobes, module, 10 * module, req.input_shaft_mm, material=profile.material)
                b = GearSpec(lobes + 1, module, 10 * module, 0, material=profile.material, internal=True)
                yield family, [Stage(a, b, float(lobes), 0.80, 0.5 * module)], "concept"


def _bearing(minimum):
    return next((dict(b) for b in BEARINGS if b["bore"] >= minimum - 1e-6), None)


def _add_check(candidate, name, value, limit, unit, detail, maximum=True, warning=False):
    passes = (value <= limit if maximum else value >= limit)
    candidate.checks.append(Check(name, "warn" if warning and passes else ("pass" if passes else "fail"), round(value, 5), round(limit, 5), unit, detail))


def _make_candidate(req, profile, family, source_stages, level):
    stages = copy.deepcopy(source_stages)
    ratio = math.prod(s.ratio for s in stages)
    efficiency = math.prod(s.efficiency for s in stages)
    signature = json.dumps({"family": family, "stages": [asdict(s) for s in stages], "mode": req.mode,
                            "profile": asdict(profile), "requirements": asdict(req)}, sort_keys=True)
    c = Candidate(hashlib.sha256(signature.encode()).hexdigest()[:12], family, stages, ratio, efficiency,
                  req.input_rpm / ratio, req.available_torque * ratio * efficiency, [], 0, None, export_level=level)
    # Input torque is calculated from the required output load, not from motor stall torque.
    rpm = req.input_rpm
    torque = req.output_torque_nm / (ratio * efficiency)
    for s in stages:
        s.input_rpm, s.input_torque_nm = rpm, torque
        torque *= s.ratio * s.efficiency
        s.output_torque_nm = torque
        rpm /= s.ratio
    wall, gap = 5., 3.
    if family in ("spur", "helical", "bevel"):
        count = len(stages) + 1
        positions = [0.]
        for s in stages:
            positions.append(positions[-1] + s.center_mm)
        z = 14.
        for i, s in enumerate(stages):
            for role, gear, shaft_index in (("driver", s.driver, i), ("driven", s.driven, i + 1)):
                c.layout.append({"name": f"stage_{i+1}_{role}", "shaft": shaft_index, "x": positions[shaft_index], "y": 0., "z": z,
                                 "rotation_deg": 0. if role == "driver" else 180. + 180. / gear.teeth,
                                 "stage": i, "role": role})
            z += max(s.driver.length_mm, s.driven.length_mm) + gap
        for idx in range(count):
            gears = ([stages[idx - 1].driven] if idx else []) + ([stages[idx].driver] if idx < len(stages) else [])
            minimum = req.input_shaft_mm if idx == 0 else (req.output_shaft_mm if idx == count - 1 else max(req.input_shaft_mm, req.output_shaft_mm))
            stock_bores = {g.bore_mm for g in gears if g.source == "catalog"}
            if len(stock_bores) > 1:
                c.checks.append(Check("Shared shaft bore compatibility", "fail", None, None, "", "Purchased gears on the intermediate shaft have different bores; no implicit reboring is allowed."))
                diameter = max(stock_bores)
            elif stock_bores:
                diameter = stock_bores.pop()
                if diameter < minimum:
                    c.checks.append(Check("Shaft interface", "fail", diameter, minimum, "mm", "Catalog bore is smaller than the requested minimum shaft."))
            else:
                selected = _bearing(minimum)
                diameter = selected["bore"] if selected else minimum
            bearing = next((dict(b) for b in BEARINGS if b["bore"] == diameter), None)
            if not bearing:
                c.checks.append(Check("Bearing availability", "fail", diameter, None, "mm", "No compatible bearing in the dimensional table."))
                bearing = dict(BEARINGS[0])
            for g in gears:
                if g.source == "print":
                    g.bore_mm = diameter
                    g.hub_diameter_mm = max(diameter + 8, 0.55 * (g.pitch_mm - 2.5 * g.module_mm))
                    g.hub_width_mm = 6.
            torque_here = stages[0].input_torque_nm if idx == 0 else stages[idx-1].output_torque_nm
            rpm_here = req.input_rpm / math.prod(s.ratio for s in stages[:idx])
            c.shafts.append({"index": idx, "x": positions[idx], "y": 0., "diameter": diameter,
                             "torque": torque_here, "rpm": rpm_here, "bearing": bearing})
        # Re-evaluate stack depth after adding print hubs.
        z = 14.
        for i, s in enumerate(stages):
            for item in c.layout:
                if item["stage"] == i:
                    item["z"] = z
            z += max(s.driver.length_mm, s.driven.length_mm) + gap
        xmin = min(l["x"] - (stages[l["stage"]].driver if l["role"] == "driver" else stages[l["stage"]].driven).outer_mm / 2 for l in c.layout)
        xmax = max(l["x"] + (stages[l["stage"]].driver if l["role"] == "driver" else stages[l["stage"]].driven).outer_mm / 2 for l in c.layout)
        radius = max(max(s.driver.outer_mm, s.driven.outer_mm) / 2 for s in stages)
        bearing_radius = max(s["bearing"]["outer"] / 2 for s in c.shafts)
        radius = max(radius, bearing_radius)
        xmin = min(xmin, -c.shafts[0]["bearing"]["outer"] / 2)
        xmax = max(xmax, positions[-1] + c.shafts[-1]["bearing"]["outer"] / 2)
        pad = wall + gap + 6
        c.size_mm = [xmax - xmin + 2 * pad, 2 * radius + 2 * pad, z + 14.]
        c.notes.append(f"Housing bounds: x_min={xmin-pad:.3f}; y_min={-radius-pad:.3f}. Dimensions include mounting flange.")
        for l in c.layout:
            l["x"] -= xmin - pad
            l["y"] += radius + pad
        for s in c.shafts:
            s["x"] -= xmin - pad
            s["y"] += radius + pad
    elif family == "planetary":
        s = stages[0]
        b1, b2 = _bearing(req.input_shaft_mm), _bearing(req.output_shaft_mm)
        if not b1 or not b2:
            return None
        s.driver.bore_mm = b1["bore"]
        s.driver.hub_diameter_mm = b1["bore"] + 8
        s.driver.hub_width_mm = 6.
        s.planet.bore_mm = 8.
        diameter = s.driven.outer_mm + 30
        c.size_mm = [diameter, diameter, s.driver.width_mm + 61]
        center = diameter / 2
        c.layout.append({"name": "sun", "x": center, "y": center, "z": 21., "rotation_deg": 0., "stage": 0, "role": "driver", "shaft": 0})
        c.layout.append({"name": "ring", "x": center, "y": center, "z": 21., "rotation_deg": 180. / s.driven.teeth if s.planet.teeth % 2 == 0 else 0., "stage": 0, "role": "driven", "shaft": -1})
        for i in range(3):
            angle = i * 2 * math.pi / 3
            c.layout.append({"name": f"planet_{i+1}", "x": center + s.center_mm * math.cos(angle), "y": center + s.center_mm * math.sin(angle),
                             "z": 21., "rotation_deg": math.degrees(angle) + 180. + 180. / s.planet.teeth - s.driver.teeth / s.planet.teeth * math.degrees(angle), "stage": 0, "role": "planet", "shaft": i + 2})
        c.shafts = [{"index": i, "x": center, "y": center, "diameter": b["bore"], "torque": t, "rpm": n, "bearing": b}
                    for i, b, t, n in [(0, b1, s.input_torque_nm, req.input_rpm), (1, b2, req.output_torque_nm, c.output_rpm)]]
        c.notes.append("Fixed ring; sun input; three-planet carrier output. Ring uses three M2 axial mounting holes and support posts; carrier/shaft hubs use 3 mm cross pins. Pin and carrier fatigue/retention require prototype verification.")
    else:
        s = stages[0]
        if family == "worm":
            c.size_mm = [s.driven.outer_mm + 45, s.driven.outer_mm + 25, 10 * s.driver.module_mm + 45]
        else:
            d = (s.driven.teeth + 6) * s.driver.module_mm + 30
            c.size_mm = [d, d, 10 * s.driver.module_mm + 45]
        c.layout = [{"name": family + "_concept", "x": c.size_mm[0]/2, "y": c.size_mm[1]/2, "z": c.size_mm[2]/2, "rotation_deg": 0., "stage": 0, "role": "driver", "shaft": 0}]
    c.backlash_deg = 0.
    for i, s in enumerate(stages):
        downstream = math.prod(st.ratio for st in stages[i+1:])
        backlash = profile.backlash_mm if "print" in (s.driver.source, s.driven.source) else 0.18
        d = s.driven.pitch_mm if family != "planetary" else s.driver.pitch_mm * s.ratio
        c.backlash_deg += math.degrees(2 * backlash / d) / downstream
    _add_check(c, "Ratio error", abs(ratio / req.ratio - 1) * 100, req.ratio_tolerance_percent, "%", "Integer tooth-count reduction relative to target.")
    _add_check(c, "Available output torque", c.available_output_nm, req.output_torque_nm, "N·m", "Motor torque at operating speed multiplied by reduction and estimated mesh efficiencies.", maximum=False)
    c.checks.append(Check("Peak motor capability", "warn", req.output_torque_nm * req.peak_factor / (ratio * efficiency), None, "N·m", "Required peak input torque. The supplied operating-speed torque/curve establishes continuous torque only; verify peak capability and duration separately."))
    for axis, actual, limit in zip("XYZ", c.size_mm, (req.max_x_mm, req.max_y_mm, req.max_z_mm)):
        _add_check(c, f"Envelope {axis}", actual, limit, "mm", "Includes housing and mounting flange; projecting external shafts are excluded.")
    _add_check(c, "Estimated output backlash", c.backlash_deg, req.max_backlash_deg, "deg", "Accumulated mesh clearance referred to output; elastic deflection and bearings are excluded.")
    if any(g.source == "print" for s in stages for g in (s.driver, s.driven)):
        _add_check(c, "Ambient temperature", req.ambient_c, profile.max_temperature_c, "°C", "Material profile screening ceiling; self-heating is uncharacterized.")
    if level == "concept":
        c.checks.append(Check("Detailed tooth/load analysis", "warn", None, None, "", "Concept search only: this family requires a validated contact geometry, thrust, lubrication and thermal model. Printable tooth exports are disabled."))
        c.notes.append("CONCEPT ONLY. Use packaging and ratio outputs for planning. No service-load rating or manufacturing tooth geometry is provided.")
    else:
        for index, s in enumerate(stages):
            effective_gear = s.planet if family == "planetary" else s.driven
            contact = external_contact_ratio(s.driver, effective_gear)
            _add_check(c, f"Stage {index+1} contact ratio", contact, 1.2, "", "Preliminary external involute transverse + overlap contact ratio.", maximum=False)
            load_share = 1.5 / s.planet_count if family == "planetary" else 1.
            tangential = 2000 * s.input_torque_nm * req.peak_factor / s.driver.pitch_mm * load_share
            speed_m_s = s.driver.pitch_mm * math.pi * s.input_rpm / 60000
            dynamic = 1 + min(speed_m_s / 10, 2)
            _add_check(c, f"Stage {index+1} pitch speed", speed_m_s, 5 if "print" in (s.driver.source, effective_gear.source) else 30, "m/s", "Conservative screening threshold; detailed thermal/wear testing is required.")
            for role, gear in (("driver", s.driver), ("planet" if family == "planetary" else "driven", effective_gear)):
                root = gear.pitch_mm - 2.5 * gear.module_mm
                _add_check(c, f"Stage {index+1} {role} hub ligament", root - gear.bore_mm, max(4, 3 * gear.module_mm), "mm", "Diametral ligament between bore and tooth root.", maximum=False)
                if gear.source == "print":
                    virtual_teeth = gear.teeth / math.cos(math.radians(gear.helix_deg)) ** 3
                    lewis = 0.484 - 2.87 / virtual_teeth
                    stress = tangential * dynamic / (min(s.driver.width_mm, effective_gear.width_mm) * gear.module_mm * lewis)
                    _add_check(c, f"Stage {index+1} {role} tooth bending", stress * req.safety_factor, profile.allowable_mpa, "MPa", "Lewis screening with peak, dynamic and requested safety factors. Does not cover fatigue, contact wear or creep.")
                    thickness = math.pi * gear.module_mm / 2 - profile.backlash_mm / 2
                    _add_check(c, f"Stage {index+1} {role} print resolution", thickness, 3 * profile.nozzle_mm, "mm", "Minimum nominal pitch tooth thickness: three nozzle widths.", maximum=False)
                else:
                    duty = s.input_torque_nm if role == "driver" else s.output_torque_nm
                    applied = duty * req.peak_factor * req.safety_factor
                    for kind, rating in (("bending", gear.bending_nm), ("catalog contact", gear.contact_nm)):
                        if rating:
                            _add_check(c, f"Stage {index+1} {role} {kind}", applied, rating, "N·m", gear.rating_conditions, warning=True)
                        else:
                            c.checks.append(Check(f"Stage {index+1} {role} {kind}", "warn", None, None, "N·m", "Catalog rating missing; cannot establish an allowable load."))
            if family == "planetary":
                c.checks.append(Check("Internal ring tooth strength", "warn", None, None, "", "Sun/planet mesh bending is screened; internal ring fatigue, planet load sharing, pin and carrier stiffness require detailed analysis."))
        for shaft in c.shafts:
            d, bearing = shaft["diameter"], shaft["bearing"]
            span = c.size_mm[2] - 16
            force = 0.
            axial = 0.
            for i, s in enumerate(stages):
                if family == "planetary":
                    force = max(force, 2000 * s.input_torque_nm * req.peak_factor / s.driver.pitch_mm)
                elif shaft["index"] in (i, i+1):
                    ft = 2000 * s.input_torque_nm * req.peak_factor / s.driver.pitch_mm
                    force += ft / math.cos(math.radians(s.driver.pressure_deg))
                    axial += ft * abs(math.tan(math.radians(s.driver.helix_deg)))
            bending_moment = force * span / 4
            normal = 32 * bending_moment / (math.pi * d**3)
            shear = 16 * shaft["torque"] * req.peak_factor * 1000 / (math.pi * d**3)
            equivalent = math.sqrt(normal**2 + 3 * shear**2) * req.safety_factor
            _add_check(c, f"Shaft {shaft['index']+1} combined stress", equivalent, 100, "MPa", "Simply supported steel shaft; 100 MPa assumed allowable. Keyway/fatigue and externally applied shaft loads are unmodeled.")
            inertia = math.pi * d**4 / 64
            deflection = force * span**3 / (48 * 200000 * inertia)
            _add_check(c, f"Shaft {shaft['index']+1} deflection", deflection, 0.05, "mm", "Worst-case central load; steel E=200 GPa.")
            equivalent_load = max(1., force / 2 + 1.6 * axial)
            life = 1e6 / (60 * shaft["rpm"]) * (bearing["dynamic_n"] / equivalent_load)**3
            _add_check(c, f"Shaft {shaft['index']+1} bearing L10", min(life, 1e12), req.life_hours, "hours", "Basic ball-bearing life using generic assumed C ratings; combined axial-load multiplier is preliminary.", maximum=False, warning=True)
            _add_check(c, f"Shaft {shaft['index']+1} bearing static", equivalent_load * req.safety_factor, bearing["static_n"], "N", "Generic assumed static rating; replace with supplier-specific bearing data.", warning=True)
            _add_check(c, f"Shaft {shaft['index']+1} bearing speed", shaft["rpm"], bearing["speed_rpm"], "rpm", "Generic conservative speed assumption.", warning=True)
    c.checks.append(Check("Service-life validation", "warn", None, None, "", "Screening result only. Contact wear, creep, lubrication, heat, housing strength, retention and fatigue need physical or validated analytical evidence."))
    if not profile.test_evidence and req.mode != "commercial":
        c.notes.append("Print material strengths are illustrative screening assumptions. No material/print-profile test evidence is attached.")
    _bom(c, req, profile)
    return c


def _bom(c, req, profile):
    for l in c.layout:
        s = c.stages[l["stage"]]
        g = s.planet if l["role"] == "planet" else (s.driver if l["role"] == "driver" else s.driven)
        if c.export_level == "concept":
            break
        density = profile.density_g_cm3 if g.source == "print" else 7.85
        volume = math.pi / 4 * (g.outer_mm**2 - g.bore_mm**2) * g.width_mm / 1000
        mass_g = volume * density * 0.85
        c.bom.append({"part": l["name"], "quantity": 1, "source": g.source, "sku": g.sku,
                      "description": f"{g.teeth} teeth, module {g.module_mm:g}, {g.width_mm:g} mm face, {g.bore_mm:g} mm bore",
                      "material": g.material, "mass_g": round(mass_g, 2),
                      "unit_cost": round(mass_g / 1000 * profile.cost_per_kg, 2) if g.source == "print" else g.price,
                      "currency": req.currency, "url": g.source_url})
    if c.export_level != "concept":
        for shaft in c.shafts:
            c.bom.append({"part": f"shaft_{shaft['index']+1}", "quantity": 1, "source": "purchase", "sku": "",
                          "description": f"Steel shaft {shaft['diameter']:g} mm; cut/machine to drawing; retention required", "material": "steel",
                          "mass_g": 0, "unit_cost": None, "currency": req.currency, "url": ""})
            c.bom.append({"part": f"bearings_shaft_{shaft['index']+1}", "quantity": 2 if c.family != "planetary" else 1, "source": "purchase",
                          "sku": shaft["bearing"]["sku"], "description": "Generic bearing dimensional code; choose manufacturer and seal type", "material": "steel",
                          "mass_g": 0, "unit_cost": None, "currency": req.currency, "url": ""})
        if c.family == "planetary":
            for name, qty, desc in [("carrier", 1, "Printed carrier, through pins and output hub"), ("planet_pins", 3, "8 mm steel pins; spacer/bushing and retention required")]:
                c.bom.append({"part": name, "quantity": qty, "source": "print" if name == "carrier" else "purchase", "sku": "", "description": desc,
                              "material": profile.material if name == "carrier" else "steel", "mass_g": 0, "unit_cost": None, "currency": req.currency, "url": ""})
        c.bom.append({"part": "housing_and_lid", "quantity": 1, "source": "print" if req.mode != "commercial" else "machine", "sku": "",
                      "description": "Split housing with bearing seats, bolt holes and mounting flange", "material": profile.material if req.mode != "commercial" else "aluminum",
                      "mass_g": 0, "unit_cost": None, "currency": req.currency, "url": ""})
        c.bom.append({"part": "assembly_hardware", "quantity": 1, "source": "purchase", "sku": "",
                      "description": "M4 housing bolts/nuts; shaft collars; gear keys or cross pins; spacers; verify lengths from CAD", "material": "steel",
                      "mass_g": 0, "unit_cost": None, "currency": req.currency, "url": ""})
    costs = [b["unit_cost"] for b in c.bom]
    # A partial material estimate must never masquerade as a complete purchase cost.
    c.estimated_cost = sum(b["unit_cost"] * b["quantity"] for b in c.bom) if costs and all(v is not None for v in costs) else None
    if req.budget:
        if c.estimated_cost is None:
            c.checks.append(Check("Budget", "warn", None, req.budget, req.currency, "Incomplete quotations; total cost cannot be checked."))
        else:
            _add_check(c, "Budget", c.estimated_cost, req.budget, req.currency, "Complete bill-of-material estimate.")


def rank(candidates, priority="balanced"):
    if not candidates:
        return
    volumes = [math.prod(c.size_mm) for c in candidates]
    min_v, max_v = min(volumes), max(volumes)
    min_b, max_b = min(c.backlash_deg for c in candidates), max(c.backlash_deg for c in candidates)
    weights = {"balanced": (0.5, 0.2, 0.3), "size": (0.85, 0.05, 0.1), "efficiency": (0.1, 0.05, 0.85), "backlash": (0.1, 0.8, 0.1), "cost": (0.6, 0.1, 0.3)}[priority]
    for c, volume in zip(candidates, volumes):
        v = (volume - min_v) / max(max_v - min_v, 1)
        b = (c.backlash_deg - min_b) / max(max_b - min_b, 0.001)
        e = 1 - c.efficiency
        c.score = round(100 * (1 - weights[0]*v - weights[1]*b - weights[2]*e) - (25 if c.export_level == "concept" else 0), 2)
        if priority == "cost" and c.estimated_cost is not None:
            c.score -= min(c.estimated_cost / 10, 50)
    candidates.sort(key=lambda c: (-c.score, c.id))
    # Pareto comparison is bounded to the displayed shortlist.
    for c in candidates[:80]:
        c.pareto = not any(math.prod(o.size_mm) <= math.prod(c.size_mm) and o.efficiency >= c.efficiency and o.backlash_deg <= c.backlash_deg
            and (math.prod(o.size_mm) < math.prod(c.size_mm) or o.efficiency > c.efficiency or o.backlash_deg < c.backlash_deg)
            for o in candidates[:80] if o is not c and o.export_level == c.export_level)


def synthesize(req: Requirements, profile: PrintProfile, catalog: Catalog, limit=60, cancel=None) -> SearchResult:
    req.validate()
    profile.validate()
    started = time.monotonic()
    rejected, seen, candidates = Counter(), set(), []
    evaluated = 0
    generators = (_parallel_sets(req, profile, catalog), _planetary_sets(req, profile, catalog), _concept_sets(req, profile))
    for generator in generators:
        for family, stages, level in generator:
            if cancel and cancel():
                raise InterruptedError("Search cancelled")
            evaluated += 1
            c = _make_candidate(req, profile, family, stages, level)
            if c is None:
                rejected["Bearing availability"] += 1
                continue
            if c.id in seen:
                continue
            seen.add(c.id)
            if c.feasible:
                candidates.append(c)
            else:
                for check in c.checks:
                    if check.status == "fail":
                        rejected[check.name] += 1
    rank(candidates, req.priority)
    explanations = []
    if req.mode == "commercial" and any(f not in ("spur", "helical") for f in req.families):
        explanations.append("Commercial synthesis currently covers parallel spur/helical meshes. Other families require additional compatible catalog and contact-model data.")
    if req.mode != "printed" and not catalog.gears(req.supplier, "helical", req.currency) and "helical" in req.families:
        explanations.append("No matching helical catalog entries. Hybrid mode can generate printed helical pairs.")
    if req.priority == "cost" and candidates and all(c.estimated_cost is None for c in candidates):
        explanations.append("Cost ranking uses size/material as a proxy because hardware quotations are incomplete. Total purchase costs remain unknown.")
    if not candidates:
        explanations.append("No candidate satisfies the modeled constraints. Review the rejection counts, increase envelope/module, reduce required torque, or import more compatible catalog gears.")
    explanations.append("All results are preliminary engineering screens. A pass does not certify fatigue life, thermal performance or manufactured fit.")
    return SearchResult(candidates[:limit], dict(rejected.most_common()), evaluated, round(time.monotonic()-started, 3), explanations)


def run_search(requirements: dict, profile: dict, catalog_text: str, limit=60) -> dict:
    catalog = Catalog()
    try:
        catalog.import_csv(catalog_text)
        return asdict(synthesize(Requirements(**requirements), PrintProfile(**profile), catalog, limit))
    finally:
        catalog.close()
