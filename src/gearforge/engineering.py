"""Traceable external involute geometry and quasi-static duty calculations.

Independent implementation of analytical involute geometry, statics and power
balance. Public manufacturer references describe the same mathematical relations;
their documents and illustrations are not bundled. No proprietary standard or
material allowable is required by this module. Units are explicit at every boundary.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields
import hashlib
import html
import json
import math
from pathlib import Path
import tempfile

from . import __version__
from .models import Candidate, Requirements, atomic_text, finite, read_text_limited, strict_json

GEOMETRY_SOURCE = "https://khkgears.net/new/gear_knowledge/gear_technical_reference/calculation_gear_dimensions.html"
FORCE_SOURCE = "https://khkgears.net/new/gear_knowledge/gear_technical_reference/gear_forces.html"
METHOD_VERSION = "external-involute-1"
STUDY_MAX_BYTES = 1_000_000


def _text(value, name, maximum=2000, required=False):
    if not isinstance(value, str) or len(value) > maximum or "\x00" in value or (required and not value.strip()):
        raise ValueError(f"Invalid {name}")


def _integer(value, name, minimum, maximum):
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError(f"{name} must be an integer between {minimum} and {maximum}")
    return value


def _model(model, data):
    if not isinstance(data, dict) or set(data) != {f.name for f in fields(model)}:
        raise ValueError(f"Missing or unknown fields in {model.__name__}")
    return model(**data)


def transverse_pressure_angle(normal_deg: float, helix_deg: float) -> float:
    """Return transverse pressure angle in radians; both inputs are degrees."""
    return math.atan(math.tan(math.radians(normal_deg)) / math.cos(math.radians(helix_deg)))


def involute(angle: float) -> float:
    return math.tan(angle) - angle


def inverse_involute(value: float) -> float:
    if not math.isfinite(value) or value <= 0:
        raise ValueError("Profile shifts produce a non-positive operating involute")
    lo, hi = 0.0, math.pi / 2 - 1e-8
    for _ in range(80):
        mid = (lo + hi) / 2
        if involute(mid) < value:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


@dataclass
class GearPair:
    normal_module_mm: float = 2.0
    pinion_teeth: int = 20
    wheel_teeth: int = 100
    normal_pressure_angle_deg: float = 20.0
    pinion_helix_angle_deg: float = 0.0
    pinion_profile_shift: float = 0.0
    wheel_profile_shift: float = 0.0
    face_width_mm: float = 20.0

    def validate(self):
        _integer(self.pinion_teeth, "Pinion teeth", 6, 1000)
        _integer(self.wheel_teeth, "Wheel teeth", 6, 1000)
        for name, lower, upper in (
            ("normal_module_mm", 0.1, 50), ("normal_pressure_angle_deg", 14, 30),
            ("pinion_helix_angle_deg", -45, 45), ("pinion_profile_shift", -1, 1.5),
            ("wheel_profile_shift", -1, 1.5), ("face_width_mm", 0.1, 1000),
        ):
            setattr(self, name, finite(getattr(self, name), name, lower, upper))


def pair_geometry(pair: GearPair) -> dict:
    pair.validate()
    mn, z1, z2 = pair.normal_module_mm, pair.pinion_teeth, pair.wheel_teeth
    an, beta = math.radians(pair.normal_pressure_angle_deg), math.radians(pair.pinion_helix_angle_deg)
    at = transverse_pressure_angle(pair.normal_pressure_angle_deg, pair.pinion_helix_angle_deg)
    mt = mn / math.cos(beta)
    x1, x2 = pair.pinion_profile_shift, pair.wheel_profile_shift
    awt = inverse_involute(involute(at) + 2 * math.tan(an) * (x1 + x2) / (z1 + z2))
    a0 = mt * (z1 + z2) / 2
    a = a0 * math.cos(at) / math.cos(awt)
    y = (a - a0) / mn
    k = x1 + x2 - y
    dw = [2 * a * z / (z1 + z2) for z in (z1, z2)]
    gears = []
    issues = []
    for role, z, x, other, diameter in zip(("pinion", "wheel"), (z1, z2), (x1, x2), (x2, x1), dw):
        d = mt * z
        db = d * math.cos(at)
        da = d + 2 * mn * (1 + y - other)
        df = d - 2 * mn * (1.25 - x)
        if df <= 0 or da <= db or da <= df:
            raise ValueError(f"{role.title()} profile is outside the supported involute geometry")
        aa = math.acos(db / da)
        s = mt * (math.pi / 2 + 2 * x * math.tan(an))
        tip_thickness = da * (s / d + involute(at) - involute(aa))
        if tip_thickness <= 0:
            issues.append(f"{role}: pointed or crossed tooth tips")
        # Equivalent-spur undercut screen is approximate for helical cutters.
        z_virtual = z / math.cos(beta) ** 3
        if z_virtual < 2 * (1 - x) / math.sin(an) ** 2 - 1e-8:
            issues.append(f"{role}: rack-generation undercut screen requires cutter/root analysis")
        gears.append(dict(reference_diameter_mm=d, base_diameter_mm=db,
                          operating_pitch_diameter_mm=diameter, tip_diameter_mm=da,
                          root_diameter_mm=df, reference_tooth_thickness_mm=s,
                          tip_tooth_thickness_mm=tip_thickness))
    rolls = [math.sqrt(g["tip_diameter_mm"] ** 2 - g["base_diameter_mm"] ** 2) / 2 for g in gears]
    tangent_length = a * math.sin(awt)
    for index, roll in enumerate(rolls):
        if roll > tangent_length + 1e-9:
            issues.append(f"{('pinion', 'wheel')[index]} addendum reaches below the mating base circle")
    base_pitch = math.pi * mt * math.cos(at)
    transverse = (sum(rolls) - tangent_length) / base_pitch
    overlap = pair.face_width_mm * abs(math.sin(beta)) / (math.pi * mn)
    if transverse < 1:
        issues.append("Transverse contact ratio is below 1; full transverse tooth contact is not maintained")
    if not 15 <= pair.normal_pressure_angle_deg <= 25 or abs(pair.pinion_helix_angle_deg) > 30 or transverse > 2.5:
        issues.append("Geometry is outside the initial development envelope: pressure 15–25°, helix ≤30°, transverse contact ratio ≤2.5")
    return dict(method=METHOD_VERSION, ratio=z2 / z1,
                transverse_module_mm=mt, transverse_pressure_angle_deg=math.degrees(at),
                operating_pressure_angle_deg=math.degrees(awt),
                operating_helix_angle_deg=math.degrees(math.atan(a / a0 * math.tan(beta))),
                reference_center_distance_mm=a0, operating_center_distance_mm=a,
                center_distance_modification_coefficient=y, tip_shortening_coefficient=k,
                transverse_base_pitch_mm=base_pitch, transverse_contact_ratio=transverse,
                overlap_contact_ratio=overlap, total_contact_ratio=transverse + overlap,
                pinion=gears[0], wheel=gears[1], issues=issues)


@dataclass
class DutyPoint:
    name: str = "Continuous rated-input target"
    input_rpm: float = 1500.0
    input_torque_nm: float = 250 * 60 / (2 * math.pi * 1500)
    duration_hours: float = 10000.0
    ambient_c: float = 25.0
    starts: int = 0

    def validate(self):
        _text(self.name, "Duty name", 120, required=True)
        for name, lower, upper in (("input_rpm", -100000, 100000),
                                   ("input_torque_nm", -1000000, 1000000),
                                   ("duration_hours", 0.000001, 1000000), ("ambient_c", -80, 200)):
            setattr(self, name, finite(getattr(self, name), name, lower, upper))
        _integer(self.starts, "Starts", 0, 1000000000)
        if self.input_rpm * self.input_torque_nm < 0:
            raise ValueError("Regenerative/braking duty needs a separate loss model; enter motoring or stationary duty")


@dataclass
class EngineeringStudy:
    name: str = "250 W steel spur qualification target"
    pair: GearPair = field(default_factory=GearPair)
    duty: list[DutyPoint] = field(default_factory=lambda: [DutyPoint()])
    target_life_hours: float = 10000.0
    ambient_min_c: float = 20.0
    ambient_max_c: float = 40.0
    assumed_efficiency: float = 0.95
    material_process: str = "Catalog steel gears; supplier grade and heat treatment to be selected"
    lubrication: str = "Enclosed lubricated housing; lubricant and quantity to be specified"
    standard_basis: str = "Open analytical involute geometry and quasi-static statics; method external-involute-1. No standards-compliance claim."
    evidence_references: str = ""
    notes: str = "Development and qualification target, not an approved operating rating."
    schema_version: int = 1

    def validate(self):
        _integer(self.schema_version, "Study schema", 1, 1)
        if not isinstance(self.pair, GearPair):
            raise ValueError("Study pair must be a GearPair")
        self.pair.validate()
        for name in ("name", "material_process", "lubrication", "standard_basis", "evidence_references", "notes"):
            _text(getattr(self, name), name, 10000 if name in ("notes", "evidence_references") else 1000, name == "name")
        for name, lower, upper in (("target_life_hours", 0.000001, 1000000),
                                   ("ambient_min_c", -80, 200), ("ambient_max_c", -80, 200),
                                   ("assumed_efficiency", 0.01, 1)):
            setattr(self, name, finite(getattr(self, name), name, lower, upper))
        if self.ambient_min_c > self.ambient_max_c:
            raise ValueError("Minimum ambient temperature exceeds maximum")
        if not isinstance(self.duty, list) or not 1 <= len(self.duty) <= 200:
            raise ValueError("Study requires 1..200 duty rows")
        names = set()
        for point in self.duty:
            if not isinstance(point, DutyPoint):
                raise ValueError("Invalid duty row")
            point.validate()
            if point.name in names:
                raise ValueError("Duty names must be unique")
            names.add(point.name)
            if not self.ambient_min_c <= point.ambient_c <= self.ambient_max_c:
                raise ValueError(f"Duty temperature is outside the design envelope: {point.name}")
        if not math.isclose(math.fsum(p.duration_hours for p in self.duty), self.target_life_hours, rel_tol=1e-9, abs_tol=1e-8):
            raise ValueError("Duty hours must sum to the target operating life")

    def save(self, path: Path):
        self.validate()
        text = json.dumps(asdict(self), indent=2, allow_nan=False)
        if len(text.encode("utf-8")) > STUDY_MAX_BYTES:
            raise ValueError("Study exceeds 1 MB")
        atomic_text(path, text)

    @classmethod
    def from_dict(cls, data):
        if not isinstance(data, dict) or not {"schema_version", "pair", "duty"} <= set(data):
            raise ValueError("Incomplete engineering study")
        data = dict(data)
        data["pair"] = _model(GearPair, data["pair"])
        if not isinstance(data["duty"], list) or len(data["duty"]) > 200:
            raise ValueError("Invalid study duty list")
        data["duty"] = [_model(DutyPoint, row) for row in data["duty"]]
        result = _model(cls, data)
        result.validate()
        return result

    @classmethod
    def load(cls, path: Path):
        return cls.from_dict(strict_json(read_text_limited(path, STUDY_MAX_BYTES, "Engineering study")))


def study_for_stage(candidate: Candidate, requirements: Requirements, stage_index: int = 0) -> EngineeringStudy:
    """Preserve the selected stage's actual load and source declarations."""
    requirements.validate()
    if candidate.family not in ("spur", "helical"):
        raise ValueError("The engineering study currently supports external spur/helical stages only")
    _integer(stage_index, "Stage index", 0, len(candidate.stages) - 1)
    stage = candidate.stages[stage_index]
    a, b = stage.driver, stage.driven
    if a.internal or b.internal or not math.isclose(a.module_mm, b.module_mm) or not math.isclose(a.pressure_deg, b.pressure_deg) or not math.isclose(a.helix_deg, -b.helix_deg, abs_tol=1e-8):
        raise ValueError("The selected gears are not a compatible external parallel-axis pair")
    result = EngineeringStudy(
        name=f"Design {candidate.id} — stage {stage_index+1} of {len(candidate.stages)}",
        pair=GearPair(normal_module_mm=a.module_mm, pinion_teeth=a.teeth, wheel_teeth=b.teeth,
                      normal_pressure_angle_deg=a.pressure_deg, pinion_helix_angle_deg=a.helix_deg,
                      face_width_mm=min(a.width_mm, b.width_mm)),
        duty=[DutyPoint(name="Required load from selected design", input_rpm=stage.input_rpm,
                        input_torque_nm=stage.input_torque_nm, duration_hours=requirements.life_hours,
                        ambient_c=requirements.ambient_c)],
        target_life_hours=requirements.life_hours, ambient_min_c=requirements.ambient_c,
        ambient_max_c=requirements.ambient_c, assumed_efficiency=stage.efficiency,
        material_process=f"Pinion: {a.material} ({a.source}, {a.sku or 'no part number'}). Wheel: {b.material} ({b.source}, {b.sku or 'no part number'}).",
        evidence_references="\n".join(value for value in (a.source_url, a.rating_conditions, b.source_url, b.rating_conditions) if value),
        notes=f"Derived from candidate {candidate.id}, stage {stage_index+1} only. Other stages, shafts, bearings and housing are not included. Supplier declarations remain unverified. Operating load is separate from the motor's available torque.",
    )
    result.validate()
    return result


def calculate_study(study: EngineeringStudy) -> dict:
    study.validate()
    geometry = pair_geometry(study.pair)
    ratio, eta = geometry["ratio"], study.assumed_efficiency
    pressure = math.radians(geometry["operating_pressure_angle_deg"])
    helix = math.radians(geometry["operating_helix_angle_deg"])
    diameter = geometry["pinion"]["operating_pitch_diameter_mm"]
    rows = []
    for point in study.duty:
        ft = 2000 * point.input_torque_nm / diameter
        fr = abs(ft) * math.tan(pressure)
        fa = ft * math.tan(helix)
        power = point.input_torque_nm * point.input_rpm * 2 * math.pi / 60
        rows.append(dict(name=point.name, input_rpm=point.input_rpm,
                         # External shafts rotate in opposite directions.
                         output_rpm=-point.input_rpm / ratio,
                         input_torque_nm=point.input_torque_nm,
                         ideal_output_torque_magnitude_nm=abs(point.input_torque_nm) * ratio,
                         estimated_output_torque_magnitude_nm=abs(point.input_torque_nm) * ratio * eta if point.input_rpm else None,
                         input_power_w=power, estimated_output_power_w=power * eta,
                         estimated_loss_power_w=power * (1 - eta),
                         tangential_force_n=ft, radial_force_magnitude_n=fr, axial_force_n=fa,
                         normal_force_magnitude_n=math.hypot(ft, fr, fa),
                         pitch_velocity_m_s=math.pi * diameter * abs(point.input_rpm) / 60000,
                         pinion_revolutions=60 * abs(point.input_rpm) * point.duration_hours,
                         wheel_revolutions=60 * abs(point.input_rpm) * point.duration_hours / ratio,
                         duration_hours=point.duration_hours, starts=point.starts, ambient_c=point.ambient_c))
    inputs = asdict(study)
    fingerprint = hashlib.sha256(json.dumps(inputs, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest()
    return dict(schema_version=1, app_version=__version__, method=METHOD_VERSION,
                study_sha256=fingerprint, inputs=inputs, geometry=geometry, duty_results=rows,
                total_input_energy_kwh=math.fsum(r["input_power_w"] * r["duration_hours"] / 1000 for r in rows),
                total_estimated_loss_energy_kwh=math.fsum(r["estimated_loss_power_w"] * r["duration_hours"] / 1000 for r in rows),
                total_pinion_revolutions=math.fsum(r["pinion_revolutions"] for r in rows),
                total_wheel_revolutions=math.fsum(r["wheel_revolutions"] for r in rows),
                production_approved=False, rated_output_torque_nm=None, rated_life_hours=None,
                references=[GEOMETRY_SOURCE, FORCE_SOURCE],
                limitations=["External parallel-axis involute pair only; ideal alignment and tooth geometry.",
                             "KHK normal-system tip shortening convention; no generated cutter root or production CAD.",
                             "Mesh forces are quasi-static; dynamics, friction force distribution and external shaft loads are excluded.",
                             "Force signs use pinion torque and helix-hand convention; shaft-coordinate reactions are not calculated.",
                             "Efficiency is a user assumption; loss power is not a thermal equilibrium calculation.",
                             "Revolutions are exposure counts, not a fatigue damage or life assessment; starts are recorded but not rated.",
                             "Material, lubricant and evidence text are declarations, not verified allowables or approval.",
                             "Fatigue/contact, bearings, shafts, housing, retention and physical qualification remain outstanding."])


def study_html(result: dict) -> str:
    esc = lambda value: html.escape(str(value))
    g = result["geometry"]
    summaries = [("Reduction", g["ratio"], ":1"), ("Operating center distance", g["operating_center_distance_mm"], "mm"),
                 ("Transverse pressure angle", g["transverse_pressure_angle_deg"], "deg"),
                 ("Operating pressure angle", g["operating_pressure_angle_deg"], "deg"),
                 ("Transverse contact ratio", g["transverse_contact_ratio"], ""),
                 ("Overlap contact ratio", g["overlap_contact_ratio"], ""),
                 ("Pinion revolutions", result["total_pinion_revolutions"], ""),
                 ("Estimated loss energy", result["total_estimated_loss_energy_kwh"], "kWh")]
    summary = "".join(f"<tr><td>{esc(name)}</td><td>{value:.8g} {unit}</td></tr>" for name, value, unit in summaries)
    rows = "".join(f"<tr><td>{esc(r['name'])}</td><td>{r['input_rpm']:.6g}</td><td>{r['input_torque_nm']:.6g}</td>"
                   f"<td>{r['duration_hours']:.6g}</td><td>{r['tangential_force_n']:.6g}</td>"
                   f"<td>{r['radial_force_magnitude_n']:.6g}</td><td>{r['axial_force_n']:.6g}</td>"
                   f"<td>{r['estimated_loss_power_w']:.6g}</td></tr>" for r in result["duty_results"])
    issues = "".join(f"<li>{esc(issue)}</li>" for issue in g["issues"])
    limits = "".join(f"<li>{esc(item)}</li>" for item in result["limitations"])
    inputs = result["inputs"]
    context = "".join(f"<h3>{label}</h3><p>{esc(inputs[key]).replace(chr(10), '<br>')}</p>"
                      for key, label in (("material_process", "Material and manufacturing"),
                                         ("lubrication", "Lubrication"), ("standard_basis", "Declared calculation basis"),
                                         ("evidence_references", "Evidence references"), ("notes", "Study notes")))
    parameters = "".join(f"<tr><td>{esc(key)}</td><td>{esc(value)}</td></tr>"
                         for key, value in inputs["pair"].items())
    dimensions = "".join(f"<tr><td>{esc(key)}</td><td>{value:.8g}</td><td>{g['wheel'][key]:.8g}</td></tr>"
                         for key, value in g["pinion"].items())
    power_rows = "".join(f"<tr><td>{esc(r['name'])}</td><td>{r['output_rpm']:.6g}</td>"
                         f"<td>{r['input_power_w']:.6g}</td><td>{r['estimated_output_power_w']:.6g}</td>"
                         f"<td>{r['ambient_c']:.6g}</td><td>{r['starts']}</td><td>{r['pinion_revolutions']:.8g}</td></tr>"
                         for r in result["duty_results"])
    return ("<!doctype html><html><head><meta charset='utf-8'><title>GearForge engineering study</title>"
            "<style>body{font-family:sans-serif;max-width:1100px;margin:24px}td,th{padding:7px;border:1px solid #888}"
            "table{border-collapse:collapse}strong{color:#9b4100}</style></head><body>"
            f"<h1>{esc(result['inputs']['name'])}</h1><p><strong>Calculated geometry and loads — no verified production rating</strong></p>"
            f"<p>Method {esc(result['method'])} · GearForge {esc(result['app_version'])}</p><table>{summary}</table>"
            f"<h2>Geometry findings</h2><ul>{issues or '<li>No findings in the implemented geometric screens; fatigue and manufacturing are not assessed.</li>'}</ul>"
            f"<h2>Duty results</h2><table><tr><th>Case</th><th>Input rpm</th><th>Input N·m</th><th>Hours</th><th>Ft N</th><th>|Fr| N</th><th>Fa N</th><th>Loss W</th></tr>{rows}</table>"
            f"<h2>Power and exposure</h2><table><tr><th>Case</th><th>Output rpm</th><th>Input W</th><th>Estimated output W</th><th>Ambient °C</th><th>Starts</th><th>Pinion revolutions</th></tr>{power_rows}</table>"
            f"<h2>Design inputs</h2><p>Target life: {inputs['target_life_hours']:.8g} h; ambient envelope: {inputs['ambient_min_c']:.6g} to {inputs['ambient_max_c']:.6g} °C; assumed efficiency: {inputs['assumed_efficiency']:.6g}.</p>"
            f"<table>{parameters}</table><h2>Gear dimensions (mm)</h2><table><tr><th>Dimension</th><th>Pinion</th><th>Wheel</th></tr>{dimensions}</table>"
            f"<h2>Declared sources and assumptions</h2>{context}"
            f"<h2>Calculation limits</h2><ul>{limits}</ul><p>Input fingerprint: {esc(result['study_sha256'])}</p></body></html>")


def export_study(study: EngineeringStudy, destination: Path) -> dict:
    """Publish inputs, results and a readable report together, without overwrite."""
    from .maintenance import write_manifest
    result = calculate_study(study)
    dest = Path(destination).absolute()
    if dest.exists() or dest.is_symlink():
        raise FileExistsError("Choose a new calculation output directory")
    dest.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".gearforge-study-", dir=dest.parent) as temporary:
        stage = Path(temporary) / "study"
        stage.mkdir()
        study.save(stage / "design.gearforge-study")
        atomic_text(stage / "calculation.json", json.dumps(result, indent=2, allow_nan=False))
        atomic_text(stage / "report.html", study_html(result))
        manifest = write_manifest(stage, kind="gearforge-engineering-study", method=METHOD_VERSION,
                                  study_sha256=result["study_sha256"], production_approved=False)
        if dest.exists() or dest.is_symlink():
            raise FileExistsError("Calculation output directory already exists")
        stage.rename(dest)
    return {"destination": str(dest), "files": len(manifest["files"]) + 1,
            "study_sha256": result["study_sha256"], "production_approved": False}
