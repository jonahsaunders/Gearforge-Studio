"""Original, piecewise-exact two-support shaft equilibrium and beam integration.

Units: mm, N, N m, MPa, radians. Right-handed axes: X along the shaft;
Y/Z transverse. Positive moments follow the right-hand rule. Bearings are
ideal radial simple supports; exactly one bearing locates the shaft axially.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
import hashlib
import html
import json
import math
from pathlib import Path
import tempfile

import numpy as np
from numpy.polynomial import Polynomial

from . import __version__
from .engineering import EngineeringStudy, _integer, _model, _text, calculate_study
from .models import atomic_text, finite, read_text_limited, strict_json

METHOD = "two-support-shaft-1"
MAX_BYTES = 2_000_000


@dataclass
class ShaftSection:
    start_mm: float = 0.0
    end_mm: float = 120.0
    outer_diameter_mm: float = 12.0
    inner_diameter_mm: float = 0.0
    youngs_modulus_mpa: float = 200000.0
    shear_modulus_mpa: float = 76923.07692307692
    material_basis: str = "Illustrative steel elastic moduli; confirm actual material and temperature"

    def validate(self):
        for name, lower, upper in (("start_mm", 0, 10000), ("end_mm", .001, 10000),
                                   ("outer_diameter_mm", .1, 1000), ("inner_diameter_mm", 0, 999.9),
                                   ("youngs_modulus_mpa", 1, 1000000), ("shear_modulus_mpa", 1, 1000000)):
            setattr(self, name, finite(getattr(self, name), name, lower, upper))
        if self.end_mm - self.start_mm < .001 or self.inner_diameter_mm >= self.outer_diameter_mm:
            raise ValueError("Each shaft section needs positive length and wall thickness")
        _text(self.material_basis, "Material basis", 2000, required=True)

    @property
    def area_mm2(self):
        return math.pi * (self.outer_diameter_mm**2 - self.inner_diameter_mm**2) / 4

    @property
    def inertia_mm4(self):
        return math.pi * (self.outer_diameter_mm**4 - self.inner_diameter_mm**4) / 64


@dataclass
class ShaftLoad:
    name: str = "External load"
    position_mm: float = 60.0
    axial_n: float = 0.0
    force_y_n: float = 0.0
    force_z_n: float = 0.0
    torque_nm: float = 0.0
    moment_y_nm: float = 0.0
    moment_z_nm: float = 0.0

    def validate(self, length):
        _text(self.name, "Load name", 120, required=True)
        self.position_mm = finite(self.position_mm, "Load position", 0, length)
        for name in ("axial_n", "force_y_n", "force_z_n", "torque_nm", "moment_y_nm", "moment_z_nm"):
            setattr(self, name, finite(getattr(self, name), name, -1e8, 1e8))


@dataclass
class ShaftCase:
    name: str = "Operating load"
    rpm: float = 1500.0
    duration_hours: float = 10000.0
    ambient_c: float = 25.0
    loads: list[ShaftLoad] = field(default_factory=lambda: [ShaftLoad(force_y_n=-100)])

    def validate(self, length):
        _text(self.name, "Case name", 120, required=True)
        self.rpm = finite(self.rpm, "Shaft speed", -100000, 100000)
        self.duration_hours = finite(self.duration_hours, "Case duration", .000001, 1e6)
        self.ambient_c = finite(self.ambient_c, "Ambient temperature", -80, 200)
        if not isinstance(self.loads, list) or not 1 <= len(self.loads) <= 100:
            raise ValueError("Each shaft case requires 1..100 loads")
        for load in self.loads:
            if not isinstance(load, ShaftLoad):raise ValueError("Invalid shaft load")
            load.validate(length)
        if len({load.name for load in self.loads}) != len(self.loads):
            raise ValueError("Load names must be unique within a case")
        balance = math.fsum(load.torque_nm for load in self.loads)
        scale = math.fsum(abs(load.torque_nm) for load in self.loads)
        if abs(balance) > 1e-9 * max(1, scale):
            raise ValueError("Applied shaft torques must balance; free-running bearings do not resist torque")


@dataclass
class ShaftStudy:
    name: str = "Shaft and bearing load study"
    length_mm: float = 120.0
    bearing_a_mm: float = 0.0
    bearing_b_mm: float = 120.0
    axial_locator: str = "a"
    sections: list[ShaftSection] = field(default_factory=lambda: [ShaftSection()])
    cases: list[ShaftCase] = field(default_factory=lambda: [ShaftCase()])
    source_study: dict | None = None
    source_description: str = "Manual load definition"
    notes: str = "Ideal rigid supports and elastic shaft. Specify actual section dimensions, support positions and material properties."
    schema_version: int = 1

    def validate(self):
        _integer(self.schema_version, "Shaft study schema", 1, 1)
        _text(self.name, "Study name", 1000, required=True)
        _text(self.notes, "Study notes", 10000)
        _text(self.source_description, "Source description", 2000)
        self.length_mm = finite(self.length_mm, "Shaft length", .01, 10000)
        self.bearing_a_mm = finite(self.bearing_a_mm, "Bearing A position", 0, self.length_mm)
        self.bearing_b_mm = finite(self.bearing_b_mm, "Bearing B position", 0, self.length_mm)
        if self.bearing_b_mm - self.bearing_a_mm < .01:
            raise ValueError("Bearing B must be at least 0.01 mm beyond bearing A")
        if self.axial_locator not in ("a", "b"):
            raise ValueError("Choose exactly one axial locating bearing: a or b")
        if not isinstance(self.sections, list) or not 1 <= len(self.sections) <= 50:
            raise ValueError("Define 1..50 contiguous shaft sections")
        previous = 0.0
        for section in self.sections:
            if not isinstance(section, ShaftSection):raise ValueError("Invalid shaft section")
            section.validate()
            # Exact boundaries prevent a small gap/overlap from changing stiffness.
            if section.start_mm != previous:
                raise ValueError("Shaft sections must cover the full length in order, without gaps or overlaps")
            previous = section.end_mm
        if previous != self.length_mm:
            raise ValueError("Shaft sections must end at the shaft length")
        if not isinstance(self.cases, list) or not 1 <= len(self.cases) <= 200:
            raise ValueError("Define 1..200 shaft load cases")
        for case in self.cases:
            if not isinstance(case, ShaftCase):raise ValueError("Invalid shaft case")
            case.validate(self.length_mm)
        if len(self.cases)*(len(self.sections)+2)+sum(len(case.loads) for case in self.cases)>2000:
            raise ValueError("Shaft study exceeds the 2,000-interval calculation bound; split the cases into separate studies")
        if len({case.name for case in self.cases}) != len(self.cases):
            raise ValueError("Shaft case names must be unique")
        if self.source_study is not None:
            # Validate and normalize the retained source; it is provenance, not approval.
            self.source_study = asdict(EngineeringStudy.from_dict(self.source_study))

    @classmethod
    def from_dict(cls, data):
        if not isinstance(data, dict):raise ValueError("Invalid shaft study")
        data = dict(data)
        for key in ("sections", "cases"):
            if not isinstance(data.get(key), list):raise ValueError(f"Missing shaft {key}")
        if len(data["sections"]) > 50 or len(data["cases"]) > 200:raise ValueError("Shaft study too large")
        data["sections"] = [_model(ShaftSection, row) for row in data["sections"]]
        cases = []
        for row in data["cases"]:
            if not isinstance(row, dict) or not isinstance(row.get("loads"), list) or len(row["loads"]) > 100:
                raise ValueError("Invalid case loads")
            row = dict(row)
            row["loads"] = [_model(ShaftLoad, value) for value in row["loads"]]
            cases.append(_model(ShaftCase, row))
        data["cases"] = cases
        result = _model(cls, data)
        result.validate()
        return result

    @classmethod
    def load(cls, path: Path):
        return cls.from_dict(strict_json(read_text_limited(path, MAX_BYTES, "Shaft study")))

    def save(self, path: Path):
        self.validate()
        text = json.dumps(asdict(self), indent=2, allow_nan=False)
        if len(text.encode("utf-8")) > MAX_BYTES:raise ValueError("Shaft study exceeds 2 MB")
        atomic_text(path, text)


def shaft_from_gear_study(source: EngineeringStudy, role="pinion", *, length_mm=120.0,
                         bearing_a_mm=0.0, bearing_b_mm=120.0, gear_position_mm=60.0,
                         coupling_position_mm=0.0, outer_diameter_mm=12.0) -> ShaftStudy:
    """Transfer every duty case, including the off-axis helical thrust couple.

    Both shafts use the same axes: X along parallel shaft axes; Y from pinion
    center to wheel center; Z completes a right-handed frame. Mesh forces are
    ideal. The balancing coupling torque excludes a friction-loss distribution.
    """
    if role not in ("pinion", "wheel"):raise ValueError("Choose pinion or wheel shaft")
    result = calculate_study(source)
    radius = result["geometry"][role]["operating_pitch_diameter_mm"] / 2
    side = 1 if role == "pinion" else -1
    cases = []
    for row in result["duty_results"]:
        fy, fz, fx = -side*row["radial_force_magnitude_n"], -side*row["tangential_force_n"], side*row["axial_force_n"]
        torque = side * radius * fz / 1000
        moment_z = -side * radius * fx / 1000
        cases.append(ShaftCase(name=row["name"], rpm=row["input_rpm"] if role == "pinion" else row["output_rpm"],
            duration_hours=row["duration_hours"], ambient_c=row["ambient_c"], loads=[
                ShaftLoad(name="Gear mesh", position_mm=gear_position_mm, axial_n=fx, force_y_n=fy, force_z_n=fz,
                          torque_nm=torque, moment_z_nm=moment_z),
                ShaftLoad(name="Coupling torque", position_mm=coupling_position_mm, torque_nm=-torque)]))
    study = ShaftStudy(name=f"{source.name} — {role} shaft", length_mm=length_mm,
        bearing_a_mm=bearing_a_mm, bearing_b_mm=bearing_b_mm,
        sections=[ShaftSection(end_mm=length_mm, outer_diameter_mm=outer_diameter_mm)], cases=cases,
        source_study=asdict(source), source_description=f"Initially derived from {role} mesh loads; source fingerprint {result['study_sha256']}. Loads remain editable.",
        notes="Initial shaft/support dimensions are an editable layout, not supplier or manufacturing geometry. Ideal mesh forces and balancing coupling torque exclude the distribution of friction losses. Both shaft axes share X; +Y points from pinion to wheel; +Z completes the right-handed frame. Include external coupling/belt forces and actual sections before component selection.")
    study.validate()
    return study


def _reactions(study: ShaftStudy, case: ShaftCase) -> tuple[ShaftLoad, ShaftLoad]:
    a, b = study.bearing_a_mm, study.bearing_b_mm
    yb = (-math.fsum(p.force_y_n*(p.position_mm-a) for p in case.loads)
          - 1000*math.fsum(p.moment_z_nm for p in case.loads)) / (b-a)
    zb = (-math.fsum(p.force_z_n*(p.position_mm-a) for p in case.loads)
          + 1000*math.fsum(p.moment_y_nm for p in case.loads)) / (b-a)
    axial = -math.fsum(p.axial_n for p in case.loads)
    return (ShaftLoad(name="Bearing A reaction", position_mm=a,
                      force_y_n=-math.fsum(p.force_y_n for p in case.loads)-yb,
                      force_z_n=-math.fsum(p.force_z_n for p in case.loads)-zb,
                      axial_n=axial if study.axial_locator == "a" else 0),
            ShaftLoad(name="Bearing B reaction", position_mm=b, force_y_n=yb, force_z_n=zb,
                      axial_n=axial if study.axial_locator == "b" else 0))


def _poly_roots_unit(poly: Polynomial) -> list[float]:
    scale = max(abs(poly.coef), default=0)
    if scale == 0:return []
    return [float(value.real) for value in (poly/scale).roots()
            if abs(value.imag) < 1e-8 and 0 < value.real < 1]


def _point(segment, position):
    t = position - segment["start_mm"]
    value = dict(position_mm=position)
    for plane in ("y", "z"):
        p = segment["polynomials"][plane]
        value[f"deflection_{plane}_mm"] = float(p(t))
        value[f"slope_{plane}_rad"] = float(p.deriv()(t))
        value[f"curvature_moment_{plane}_nmm"] = segment[f"m_{plane}"] + segment[f"shear_{plane}"] * t
    value["deflection_magnitude_mm"] = math.hypot(value["deflection_y_mm"], value["deflection_z_mm"])
    value["slope_magnitude_rad"] = math.hypot(value["slope_y_rad"], value["slope_z_rad"])
    value["bending_moment_magnitude_nm"] = math.hypot(value["curvature_moment_y_nmm"], value["curvature_moment_z_nmm"])/1000
    value["axial_displacement_mm"] = segment["axial_start_mm"] + segment["axial_strain"]*t
    value["twist_rad"] = segment["twist_start_rad"] + segment["twist_per_mm"]*t
    section = segment["section"]
    sigma = abs(segment["axial_n"])/section.area_mm2 + value["bending_moment_magnitude_nm"]*1000*section.outer_diameter_mm/(2*section.inertia_mm4)
    tau = abs(segment["torque_nmm"])*section.outer_diameter_mm/(4*section.inertia_mm4)
    value["nominal_surface_normal_mpa"] = sigma
    value["nominal_surface_torsion_mpa"] = tau
    value["nominal_surface_von_mises_mpa"] = math.hypot(sigma, math.sqrt(3)*tau)
    value["axial_force_n"] = segment["axial_n"]
    value["torque_nm"] = segment["torque_nmm"]/1000
    value["shear_y_n"] = segment["shear_y"]
    value["shear_z_n"] = segment["shear_z"]
    return value


def solve_shaft_case(study: ShaftStudy, case_index=0) -> dict:
    study.validate()
    _integer(case_index, "Case index", 0, len(study.cases)-1)
    return _solve_validated_case(study, case_index)


def _solve_validated_case(study: ShaftStudy, case_index: int) -> dict:
    case = study.cases[case_index]
    ra, rb = _reactions(study, case)
    loads = [*case.loads, ra, rb]
    positions = sorted({0., study.length_mm, *[p.position_mm for p in loads],
                        *[s.start_mm for s in study.sections], *[s.end_mm for s in study.sections]})
    segments = []
    previous_y = previous_z = slope_y = slope_z = axial = twist = 0.0
    for start, end in zip(positions, positions[1:]):
        section = next(s for s in study.sections if s.start_mm <= start and s.end_mm >= end)
        left = [p for p in loads if p.position_mm <= start]
        shear_y = math.fsum(p.force_y_n for p in left)
        shear_z = math.fsum(p.force_z_n for p in left)
        my = math.fsum(p.force_y_n*(start-p.position_mm)-p.moment_z_nm*1000 for p in left)
        mz = math.fsum(p.force_z_n*(start-p.position_mm)+p.moment_y_nm*1000 for p in left)
        ei = section.youngs_modulus_mpa*section.inertia_mm4
        py = Polynomial([previous_y, slope_y, my/(2*ei), shear_y/(6*ei)])
        pz = Polynomial([previous_z, slope_z, mz/(2*ei), shear_z/(6*ei)])
        force_x = -math.fsum(p.axial_n for p in left)
        torque = -1000*math.fsum(p.torque_nm for p in left)
        axial_strain = force_x/(section.youngs_modulus_mpa*section.area_mm2)
        twist_per_mm = torque/(section.shear_modulus_mpa*2*section.inertia_mm4)
        segments.append(dict(start_mm=start, end_mm=end, section=section,
            polynomials=dict(y=py,z=pz), m_y=my, m_z=mz, shear_y=shear_y, shear_z=shear_z,
            axial_n=force_x, torque_nmm=torque, axial_start_mm=axial, axial_strain=axial_strain,
            twist_start_rad=twist, twist_per_mm=twist_per_mm))
        h = end-start
        previous_y, previous_z = float(py(h)), float(pz(h))
        slope_y, slope_z = float(py.deriv()(h)), float(pz.deriv()(h))
        axial += axial_strain*h
        twist += twist_per_mm*h
    def at(position):
        segment = next(s for s in segments if s["start_mm"] <= position <= s["end_mm"])
        return _point(segment, position)
    # Uniform integration constants enforce y(a)=y(b)=z(a)=z(b)=0 even for
    # overhangs and changes in EI. Section interfaces retain slope continuity.
    raw_a, raw_b = at(study.bearing_a_mm), at(study.bearing_b_mm)
    for plane in ("y", "z"):
        gradient = -(raw_b[f"deflection_{plane}_mm"]-raw_a[f"deflection_{plane}_mm"])/(study.bearing_b_mm-study.bearing_a_mm)
        intercept = -raw_a[f"deflection_{plane}_mm"]-gradient*study.bearing_a_mm
        for segment in segments:
            segment["polynomials"][plane] += Polynomial([intercept+gradient*segment["start_mm"], gradient])
    axial_offset = at(study.bearing_a_mm if study.axial_locator == "a" else study.bearing_b_mm)["axial_displacement_mm"]
    for segment in segments:segment["axial_start_mm"] -= axial_offset
    extrema = []
    samples = []
    for index, segment in enumerate(segments):
        start, end = segment["start_mm"], segment["end_mm"]
        h = end-start
        py, pz = (segment["polynomials"][p](Polynomial([0,h])) for p in ("y","z"))
        fractions = {0., 1., *_poly_roots_unit(py*py.deriv()+pz*pz.deriv()),
                     *_poly_roots_unit(py.deriv()*py.deriv(2)+pz.deriv()*pz.deriv(2))}
        for fraction in sorted(fractions):
            point = _point(segment, start+fraction*h)
            point["segment_index"] = index
            extrema.append(point)
        for fraction in np.linspace(0,1,9):samples.append(_point(segment, start+float(fraction)*h))
    maxima = {}
    for name in ("deflection_magnitude_mm", "slope_magnitude_rad", "bending_moment_magnitude_nm", "nominal_surface_von_mises_mpa"):
        worst = max(extrema, key=lambda p:p[name])
        maxima[name] = dict(value=worst[name], position_mm=worst["position_mm"], segment_index=worst["segment_index"])
    bearing_results = []
    for name, reaction in (("a",ra),("b",rb)):
        bearing_results.append(dict(name=name, position_mm=reaction.position_mm,
            reaction_on_shaft_x_n=reaction.axial_n, reaction_on_shaft_y_n=reaction.force_y_n,
            reaction_on_shaft_z_n=reaction.force_z_n, radial_load_n=math.hypot(reaction.force_y_n,reaction.force_z_n),
            axial_load_n=abs(reaction.axial_n), slope_magnitude_rad=at(reaction.position_mm)["slope_magnitude_rad"]))
    residual = dict(force_x_n=math.fsum(p.axial_n for p in loads),force_y_n=math.fsum(p.force_y_n for p in loads),
                    force_z_n=math.fsum(p.force_z_n for p in loads), torque_x_nm=math.fsum(p.torque_nm for p in loads),
                    moment_y_nm=math.fsum(p.moment_y_nm-p.position_mm*p.force_z_n/1000 for p in loads),
                    moment_z_nm=math.fsum(p.moment_z_nm+p.position_mm*p.force_y_n/1000 for p in loads))
    findings = []
    span = study.bearing_b_mm-study.bearing_a_mm
    if span/max(s.outer_diameter_mm for s in study.sections) < 10:
        findings.append("Support span / maximum diameter is below 10; shear deformation may be material and is not modeled.")
    if maxima["slope_magnitude_rad"]["value"] > .05 or maxima["deflection_magnitude_mm"]["value"] > .01*span:
        findings.append("Small-deflection assumptions exceeded: slope >0.05 rad or deflection >1% support span.")
    if any(s["axial_n"] < 0 for s in segments):
        findings.append("Compression is present; column buckling and beam-column effects are not assessed.")
    return dict(name=case.name,rpm=case.rpm,duration_hours=case.duration_hours,ambient_c=case.ambient_c,
                revolutions=60*abs(case.rpm)*case.duration_hours,bearings=bearing_results,maxima=maxima,
                equilibrium_residual=residual,load_stations=[dict(name=p.name,**at(p.position_mm)) for p in case.loads],
                samples=samples,critical_points=extrema,findings=findings,
                end_to_end_twist_rad=at(study.length_mm)["twist_rad"]-at(0)["twist_rad"])


def calculate_shaft_study(study: ShaftStudy) -> dict:
    study.validate()
    cases = [_solve_validated_case(study,i) for i in range(len(study.cases))]
    inputs = asdict(study)
    digest = hashlib.sha256(json.dumps(inputs,sort_keys=True,separators=(",",":"),allow_nan=False).encode()).hexdigest()
    return dict(schema_version=1,app_version=__version__,method=METHOD,study_sha256=digest,inputs=inputs,cases=cases,
        total_hours=math.fsum(c.duration_hours for c in study.cases),production_approved=False,rated_life_hours=None,
        limitations=["Linear elastic Euler–Bernoulli bending, Saint-Venant torsion and axial extension; rigid ideal simple radial supports, one axial locator.",
            "Point forces/couples on circular concentric solid or hollow sections. Distributed loads, support compliance, preload, bearing stiffness, shear deformation and dynamics are excluded.",
            "Nominal surface stress combines axial/bending normal stress and torsion. Transverse shear stress, shoulder/keyway concentration, residual stress and fatigue are excluded.",
            "Material moduli and load definitions are user declarations. No yield, fatigue or material allowable is inferred from a name.",
            "Bearing reactions are component loads, not bearing life/capacity ratings. Actual bearing arrangement and permissible misalignment must be checked.",
            "A retained gear study records initial provenance; edited shaft loads are not automatically synchronized with it.",
            "Twist is relative to X=0. Sampling is for drawing; deflection/slope extrema use polynomial stationary points and section boundaries.",
            "No production fatigue, service-life or assembled gearbox approval is established."])


def shaft_report_html(result: dict) -> str:
    esc=lambda value:html.escape(str(value))
    pieces=[]
    for case in result["cases"]:
        bearings="".join(f"<tr><td>{b['name'].upper()}</td><td>{b['position_mm']:.8g}</td><td>{b['radial_load_n']:.8g}</td><td>{b['axial_load_n']:.8g}</td><td>{b['slope_magnitude_rad']:.8g}</td></tr>" for b in case["bearings"])
        maxima="".join(f"<tr><td>{esc(key.replace('_',' '))}</td><td>{row['value']:.8g}</td><td>{row['position_mm']:.8g}</td></tr>" for key,row in case["maxima"].items())
        loads="".join(f"<tr><td>{esc(p['name'])}</td><td>{p['position_mm']:.8g}</td><td>{p['deflection_y_mm']:.8g}</td><td>{p['deflection_z_mm']:.8g}</td><td>{p['slope_magnitude_rad']:.8g}</td><td>{p['twist_rad']:.8g}</td></tr>" for p in case["load_stations"])
        findings="".join(f"<li>{esc(f)}</li>" for f in case["findings"])
        pieces.append(f"<h2>{esc(case['name'])}</h2><p>{case['rpm']:.8g} rpm · {case['duration_hours']:.8g} h · {case['ambient_c']:.8g} °C</p>"
            f"<h3>Bearing loads</h3><table><tr><th>Bearing</th><th>X mm</th><th>Radial N</th><th>Axial N</th><th>Slope rad</th></tr>{bearings}</table>"
            f"<h3>Section extrema</h3><table><tr><th>Quantity</th><th>Value</th><th>X mm</th></tr>{maxima}</table>"
            f"<h3>Load station motion</h3><table><tr><th>Load</th><th>X mm</th><th>Y mm</th><th>Z mm</th><th>Slope rad</th><th>Twist rad</th></tr>{loads}</table>"
            f"<h3>Model findings</h3><ul>{findings or '<li>No additional domain flags. Strength and fatigue remain unassessed.</li>'}</ul>")
    inputs=result["inputs"]
    sections="".join(f"<tr><td>{s['start_mm']:.8g}–{s['end_mm']:.8g}</td><td>{s['outer_diameter_mm']:.8g}</td><td>{s['inner_diameter_mm']:.8g}</td><td>{s['youngs_modulus_mpa']:.8g}</td><td>{s['shear_modulus_mpa']:.8g}</td><td>{esc(s['material_basis'])}</td></tr>" for s in inputs["sections"])
    applied="".join(f"<tr><td>{esc(case['name'])}</td><td>{esc(p['name'])}</td><td>{p['position_mm']:.8g}</td><td>{p['axial_n']:.8g}</td><td>{p['force_y_n']:.8g}</td><td>{p['force_z_n']:.8g}</td><td>{p['torque_nm']:.8g}</td><td>{p['moment_y_nm']:.8g}</td><td>{p['moment_z_nm']:.8g}</td></tr>" for case in inputs["cases"] for p in case["loads"])
    limits="".join(f"<li>{esc(item)}</li>" for item in result["limitations"])
    return ("<!doctype html><html><head><meta charset='utf-8'><title>GearForge shaft study</title><style>body{font-family:sans-serif;margin:24px;max-width:1200px}table{border-collapse:collapse}td,th{border:1px solid #888;padding:6px}</style></head><body>"
        f"<h1>{esc(inputs['name'])}</h1><p><strong>Elastic shaft and bearing loads — no verified production rating</strong></p>"
        f"<p>Method {esc(result['method'])} · GearForge {esc(result['app_version'])}</p>"
        f"<p>Length {inputs['length_mm']:.8g} mm; supports at {inputs['bearing_a_mm']:.8g} and {inputs['bearing_b_mm']:.8g} mm; axial locator {esc(inputs['axial_locator']).upper()}.</p>"
        +"".join(pieces)+f"<h2>Section inputs</h2><table><tr><th>X range mm</th><th>OD mm</th><th>ID mm</th><th>E MPa</th><th>G MPa</th><th>Basis</th></tr>{sections}</table>"
        f"<h2>Applied loads</h2><table><tr><th>Case</th><th>Load</th><th>X mm</th><th>Fx N</th><th>Fy N</th><th>Fz N</th><th>Tx N·m</th><th>My N·m</th><th>Mz N·m</th></tr>{applied}</table>"
        f"<h2>Provenance and notes</h2><p>{esc(inputs['source_description'])}</p><p>{esc(inputs['notes'])}</p>"
        f"<h2>Limits</h2><ul>{limits}</ul><p>Input fingerprint: {esc(result['study_sha256'])}</p></body></html>")


def export_shaft_study(study: ShaftStudy, destination: Path) -> dict:
    from .maintenance import write_manifest
    result=calculate_shaft_study(study)
    dest=Path(destination).absolute()
    if dest.exists() or dest.is_symlink():raise FileExistsError("Choose a new shaft calculation directory")
    dest.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".gearforge-shaft-",dir=dest.parent) as temporary:
        stage=Path(temporary)/"study";stage.mkdir()
        study.save(stage/"design.gearforge-shaft")
        atomic_text(stage/"calculation.json",json.dumps(result,indent=2,allow_nan=False))
        atomic_text(stage/"report.html",shaft_report_html(result))
        manifest=write_manifest(stage,kind="gearforge-shaft-study",method=METHOD,study_sha256=result["study_sha256"],production_approved=False)
        if dest.exists() or dest.is_symlink():raise FileExistsError("Shaft output directory already exists")
        stage.rename(dest)
    return dict(destination=str(dest),files=len(manifest["files"])+1,study_sha256=result["study_sha256"],production_approved=False)
