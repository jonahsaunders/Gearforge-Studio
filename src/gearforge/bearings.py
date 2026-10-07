"""Original basic bearing fatigue arithmetic using explicit declared inputs.

No supplier factor table, material allowable or standards text is bundled.
The retained shaft study is recalculated; bearing loads are never cached inputs.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
import hashlib
import html
import json
import math
from pathlib import Path
import tempfile

from . import __version__
from .engineering import _integer, _model, _text
from .models import atomic_text, finite, read_text_limited, strict_json
from .shafts import ShaftStudy, calculate_shaft_study

METHOD = "basic-bearing-duty-1"
MAX_BYTES = 3_000_000
KINDS = {"deep_groove_ball": 3.0, "cylindrical_roller_radial": 10 / 3}


def optional_number(value, name, lower, upper):
    return None if value is None else finite(value, name, lower, upper)


@dataclass
class BearingDefinition:
    position: str = "a"
    kind: str = "deep_groove_ball"
    manufacturer: str = ""
    designation: str = "Unspecified bearing"
    bore_mm: float | None = None
    dynamic_capacity_n: float | None = None
    static_capacity_n: float | None = None
    speed_limit_rpm: float | None = None
    minimum_dynamic_load_n: float | None = None
    axial_limit_n: float | None = None
    misalignment_limit_rad: float | None = None
    minimum_temperature_c: float | None = None
    maximum_temperature_c: float | None = None
    required_static_safety: float | None = None
    data_status: str = "unverified"
    source_reference: str = ""
    rating_conditions: str = ""
    redistribution_basis: str = ""

    def validate(self):
        if self.position not in ("a", "b") or self.kind not in KINDS:
            raise ValueError("Choose bearing A/B and a supported bearing type")
        if self.data_status not in ("unverified", "synthetic", "declared"):
            raise ValueError("Invalid bearing data status")
        for key in ("manufacturer", "designation", "source_reference", "rating_conditions", "redistribution_basis"):
            _text(getattr(self, key), key, 3000, required=key == "designation")
        for key, lower, upper in (
            ("bore_mm", .1, 1000), ("dynamic_capacity_n", .001, 1e9),
            ("static_capacity_n", .001, 1e9), ("speed_limit_rpm", .001, 1e6),
            ("minimum_dynamic_load_n", 0, 1e9), ("axial_limit_n", 0, 1e9),
            ("misalignment_limit_rad", 0, .5), ("minimum_temperature_c", -80, 200),
            ("maximum_temperature_c", -80, 200), ("required_static_safety", .1, 100),
        ):
            setattr(self, key, optional_number(getattr(self, key), key, lower, upper))
        if (self.minimum_temperature_c is not None and self.maximum_temperature_c is not None
                and self.minimum_temperature_c > self.maximum_temperature_c):
            raise ValueError("Bearing temperature limits are reversed")


@dataclass
class BearingCase:
    case_name: str = "Operating load"
    position: str = "a"
    motion: str = "continuous_rotation"
    operating_temperature_c: float | None = None
    installation_misalignment_rad: float | None = None
    dynamic_x: float | None = None
    dynamic_y: float | None = None
    static_x: float | None = None
    static_y: float | None = None
    factor_basis: str = ""

    def validate(self):
        _text(self.case_name, "Bearing duty case", 120, required=True)
        _text(self.factor_basis, "Bearing factor basis", 3000)
        if self.position not in ("a", "b") or self.motion not in ("continuous_rotation", "stationary", "oscillation"):
            raise ValueError("Invalid bearing case position or motion")
        self.operating_temperature_c = optional_number(self.operating_temperature_c, "Bearing operating temperature", -80, 200)
        self.installation_misalignment_rad = optional_number(self.installation_misalignment_rad, "Installation misalignment", 0, .5)
        for key in ("dynamic_x", "dynamic_y", "static_x", "static_y"):
            setattr(self, key, optional_number(getattr(self, key), key, 0, 100))


@dataclass
class BearingStudy:
    name: str = "Bearing duty assessment"
    shaft: ShaftStudy = field(default_factory=ShaftStudy)
    bearings: list[BearingDefinition] = field(default_factory=lambda: [BearingDefinition(), BearingDefinition(position="b")])
    cases: list[BearingCase] = field(default_factory=lambda: [BearingCase(), BearingCase(position="b")])
    required_hours: float = 10000.0
    notes: str = "Enter exact bearing rating conditions and every load case. Basic L10 is a per-bearing population estimate, not gearbox service life."
    schema_version: int = 1

    def validate(self):
        _integer(self.schema_version, "Bearing schema", 1, 1)
        _text(self.name, "Bearing study name", 1000, required=True)
        _text(self.notes, "Bearing notes", 10000)
        self.required_hours = finite(self.required_hours, "Required duty hours", .000001, 2e8)
        if not isinstance(self.shaft, ShaftStudy):raise ValueError("A complete shaft study is required")
        self.shaft.validate()
        if not isinstance(self.bearings, list) or len(self.bearings) != 2:
            raise ValueError("Define exactly two bearings")
        for bearing in self.bearings:
            if not isinstance(bearing, BearingDefinition):raise ValueError("Invalid bearing definition")
            bearing.validate()
        if {b.position for b in self.bearings} != {"a", "b"}:raise ValueError("Define bearing A and B once each")
        if not isinstance(self.cases, list) or len(self.cases) != 2 * len(self.shaft.cases):
            raise ValueError("Each shaft case requires separate bearing A and B conditions")
        for case in self.cases:
            if not isinstance(case, BearingCase):raise ValueError("Invalid bearing case")
            case.validate()
        expected = {(c.name, p) for c in self.shaft.cases for p in ("a", "b")}
        if {(c.case_name, c.position) for c in self.cases} != expected:
            raise ValueError("Bearing cases must match every retained shaft case exactly")
        speeds = {c.name: c.rpm for c in self.shaft.cases}
        for case in self.cases:
            if (case.motion == "stationary") != (speeds[case.case_name] == 0) and case.motion != "oscillation":
                raise ValueError("Stationary cases require zero shaft speed; rotating cases require nonzero speed")

    @classmethod
    def from_dict(cls, data):
        if not isinstance(data, dict):raise ValueError("Invalid bearing study")
        data = dict(data)
        if not isinstance(data.get("bearings"), list) or len(data["bearings"]) != 2:
            raise ValueError("Missing bearing definitions")
        if not isinstance(data.get("cases"), list) or len(data["cases"]) > 400:
            raise ValueError("Missing or excessive bearing cases")
        data["shaft"] = ShaftStudy.from_dict(data.get("shaft"))
        data["bearings"] = [_model(BearingDefinition, row) for row in data["bearings"]]
        data["cases"] = [_model(BearingCase, row) for row in data["cases"]]
        result = _model(cls, data);result.validate();return result

    @classmethod
    def load(cls, path):
        return cls.from_dict(strict_json(read_text_limited(Path(path), MAX_BYTES, "Bearing study")))

    def save(self, path):
        self.validate();text = json.dumps(asdict(self), indent=2, allow_nan=False)
        if len(text.encode("utf-8")) > MAX_BYTES:raise ValueError("Bearing study exceeds 3 MB")
        atomic_text(Path(path), text)


def bearings_from_shaft(shaft: ShaftStudy) -> BearingStudy:
    # Copy the input, never a calculated/cached shaft result.
    shaft = ShaftStudy.from_dict(asdict(shaft))
    study = BearingStudy(name=f"{shaft.name} — bearings", shaft=shaft,
        cases=[BearingCase(case_name=c.name, position=p, motion="stationary" if c.rpm == 0 else "continuous_rotation")
               for c in shaft.cases for p in ("a", "b")],
        required_hours=math.fsum(c.duration_hours for c in shaft.cases))
    study.validate();return study


def synthetic_bearing_example(shaft: ShaftStudy | None = None) -> BearingStudy:
    if shaft is None:
        from .engineering import EngineeringStudy
        from .shafts import shaft_from_gear_study
        shaft = shaft_from_gear_study(EngineeringStudy())
    study = bearings_from_shaft(shaft)
    study.name = "Synthetic bearing arithmetic example — not a supplier selection"
    for bearing in study.bearings:
        bearing.designation = "GearForge synthetic radial ball fixture"
        bearing.bore_mm = 12; bearing.dynamic_capacity_n = 500; bearing.static_capacity_n = 250
        bearing.speed_limit_rpm = 5000; bearing.minimum_dynamic_load_n = 5; bearing.axial_limit_n = 50
        bearing.misalignment_limit_rad = .001; bearing.minimum_temperature_c = 20; bearing.maximum_temperature_c = 80
        bearing.required_static_safety = 2; bearing.data_status = "synthetic"
        bearing.source_reference = "Original GearForge synthetic verification inputs; no manufacturer product"
        bearing.rating_conditions = "Invented constant limits for testing only; not material or supplier evidence"
        bearing.redistribution_basis = "GearForge-authored fixture, Apache-2.0"
    for case in study.cases:
        case.operating_temperature_c = 40;case.installation_misalignment_rad = 0
    return study


def _check(checks, name, actual, limit, *, maximum=True, note=""):
    state = "unassessed" if actual is None or limit is None else (
        "within_limit" if (actual <= limit if maximum else actual >= limit) else "outside_limit")
    checks.append(dict(name=name, state=state, actual=actual, limit=limit, note=note))


def _finite_ratio(numerator, denominator):
    if denominator == 0:return None
    value = numerator / denominator
    return value if math.isfinite(value) else None


def _basic_revolutions(capacity, load, exponent):
    if capacity is None or load is None or load == 0:return None
    logarithm = math.log(1e6) + exponent * (math.log(capacity) - math.log(load))
    return math.exp(logarithm) if logarithm < 709 else None


def calculate_bearing_study(study: BearingStudy) -> dict:
    study.validate()
    shaft = calculate_shaft_study(study.shaft)
    conditions = {(c.case_name, c.position): c for c in study.cases}
    total_hours = shaft["total_hours"]
    results = []
    for bearing in sorted(study.bearings, key=lambda b: b.position):
        exponent = KINDS[bearing.kind]; rows = []; checks = []
        source_complete = bearing.data_status == "declared" and all(
            value.strip() for value in (bearing.manufacturer, bearing.source_reference, bearing.rating_conditions))
        checks.append(dict(name="Rating provenance", state="within_limit" if source_complete else "unassessed",
            actual=bearing.data_status, limit="declared manufacturer, source and applicable conditions",
            note="A declaration is retained evidence, not an independent review. Synthetic values are never a product selection."))
        position = study.shaft.bearing_a_mm if bearing.position == "a" else study.shaft.bearing_b_mm
        diameters = {s.outer_diameter_mm for s in study.shaft.sections if s.start_mm <= position <= s.end_mm}
        seat_diameter = next(iter(diameters)) if len(diameters) == 1 else None
        bore_matches = None if seat_diameter is None or bearing.bore_mm is None else int(math.isclose(seat_diameter, bearing.bore_mm, abs_tol=1e-8, rel_tol=0))
        _check(checks, "Nominal seat/bore match", bore_matches, 1, maximum=False,
               note="Point-support diameter only; width, fit, clearance and shoulders require the manufacturing definition.")
        for case in shaft["cases"]:
            condition = conditions[case["name"], bearing.position]
            reaction = next(row for row in case["bearings"] if row["name"] == bearing.position)
            radial, axial = reaction["radial_load_n"], reaction["axial_load_n"]
            speed = abs(case["rpm"]); revolutions = 60 * speed * case["duration_hours"]
            row_checks = []
            supported = not (bearing.kind == "cylindrical_roller_radial" and axial > 0)
            if not supported:
                dynamic = static = None
                row_checks.append(dict(name="Bearing axial-load model", state="unassessed", actual=axial, limit=0,
                    note="This cylindrical-roller model carries radial load only; flange/axial capacity is not modeled."))
            elif axial == 0:
                dynamic = static = radial
            else:
                def combined(x, y):
                    if x is None or y is None or not condition.factor_basis.strip():return None
                    return max(radial, x * radial + y * axial) if x * radial + y * axial > 0 else None
                dynamic = combined(condition.dynamic_x, condition.dynamic_y)
                static = combined(condition.static_x, condition.static_y)
                for name, value in (("Dynamic combined-load factors", dynamic), ("Static combined-load factors", static)):
                    if condition.motion == "stationary" and name.startswith("Dynamic"):continue
                    row_checks.append(dict(name=name, state="within_limit" if value is not None else "unassessed",
                        actual=value, limit="case-specific X/Y and documented branch/conditions",
                        note="Factors are user declarations; no supplier table or induced-thrust arrangement is inferred."))
            if condition.motion == "oscillation":
                revolutions = None
                row_checks.append(dict(name="Motion model", state="unassessed", actual="oscillation", limit="continuous rotation or stationary",
                    note="Shaft rpm cannot establish oscillation contact exposure; basic rolling life is unavailable."))
            capacity = bearing.dynamic_capacity_n
            damage = None if revolutions is None or (revolutions > 0 and (dynamic is None or capacity is None)) else (
                0.0 if revolutions == 0 else revolutions / 1e6 * (dynamic / capacity) ** exponent)
            basic_revolutions = _basic_revolutions(capacity, dynamic, exponent)
            static_safety = None if static is None or bearing.static_capacity_n is None else _finite_ratio(bearing.static_capacity_n, static)
            static_limit = None if bearing.static_capacity_n is None or bearing.required_static_safety is None else bearing.static_capacity_n / bearing.required_static_safety
            _check(row_checks, "Static load at required safety N", static, static_limit,
                   note="Limit is C0 / required static safety; check every stationary and short-duration peak case. Zero load has no finite safety ratio.")
            _check(row_checks, "Speed rpm", speed, bearing.speed_limit_rpm)
            _check(row_checks, "Axial load N", axial, bearing.axial_limit_n)
            if speed > 0:
                _check(row_checks, "Minimum equivalent dynamic load N", dynamic, bearing.minimum_dynamic_load_n, maximum=False,
                       note="Use the supplier minimum applicable to speed, acceleration, lubrication and bearing type.")
            _check(row_checks, "Minimum bearing temperature °C", condition.operating_temperature_c, bearing.minimum_temperature_c, maximum=False)
            _check(row_checks, "Maximum bearing temperature °C", condition.operating_temperature_c, bearing.maximum_temperature_c)
            misalignment = None if condition.installation_misalignment_rad is None else reaction["slope_magnitude_rad"] + condition.installation_misalignment_rad
            _check(row_checks, "Conservative bearing misalignment rad", misalignment, bearing.misalignment_limit_rad,
                   note="Shaft slope plus installation/housing-axis error magnitude; rigid support assumptions remain.")
            if case["findings"]:
                row_checks.append(dict(name="Shaft model domain", state="unassessed", actual=case["findings"], limit="resolved domain concerns", note="Load-path findings affect use of the motion result."))
            rows.append(dict(name=case["name"], rpm=case["rpm"], duration_hours=case["duration_hours"], motion=condition.motion,
                radial_load_n=radial, axial_load_n=axial, equivalent_dynamic_n=dynamic, equivalent_static_n=static,
                revolutions=revolutions, basic_l10_revolutions=basic_revolutions, cycle_damage=damage,
                static_safety=static_safety, shaft_slope_rad=reaction["slope_magnitude_rad"],
                conservative_misalignment_rad=misalignment, checks=row_checks))
        damage_complete = all(row["cycle_damage"] is not None for row in rows)
        cycle_damage = math.fsum(row["cycle_damage"] for row in rows) if damage_complete else None
        target_damage = None if cycle_damage is None else cycle_damage * study.required_hours / total_hours
        rolling_life = _finite_ratio(total_hours, cycle_damage) if cycle_damage is not None else None
        # Zero modeled fatigue demand is not an infinite physical life claim.
        _check(checks, "Basic L10 target damage", target_damage if rolling_life is not None else None, 1,
               note="Per-bearing 90% basic fatigue population model for repeated duty; not adjusted service life or assembly reliability.")
        all_checks = checks + [check for row in rows for check in row["checks"]]
        state = ("outside_entered_limits" if any(c["state"] == "outside_limit" for c in all_checks) else
                 "incomplete" if any(c["state"] == "unassessed" for c in all_checks) else "within_entered_limits")
        if bearing.data_status == "synthetic":
            state = "synthetic_outside_entered_limits" if state == "outside_entered_limits" else "synthetic_example"
        results.append(dict(position=bearing.position, designation=bearing.designation, kind=bearing.kind, exponent=exponent,
            assessment=state, cases=rows, checks=checks, cycle_damage=cycle_damage, target_damage=target_damage,
            basic_l10_repeated_duty_hours=rolling_life, production_approved=False))
    inputs = asdict(study)
    digest = hashlib.sha256(json.dumps(inputs, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()
    return dict(schema_version=1, app_version=__version__, method=METHOD, study_sha256=digest, inputs=inputs,
        shaft_study_sha256=shaft["study_sha256"], duty_period_hours=total_hours, required_hours=study.required_hours,
        bearings=results, production_approved=False, rated_gearbox_life_hours=None,
        limitations=[
            "Basic L10 is per-bearing rolling-contact fatigue at 90% population survival; it is not an individual life guarantee, pair reliability or gearbox service life.",
            "Only deep-groove radial ball bearings and radial-only cylindrical rollers are modeled. Preload, induced axial forces, angular-contact/tapered arrangements and oscillation life are excluded.",
            "Combined-load factors and all operating limits must apply to the exact product, clearance, loading and temperature. Declarations are not independently approved.",
            "Damage sums full revolutions at absolute speed across repeated duty. Stationary loads receive static checks; fretting and false brinelling are excluded.",
            "Lubrication, contamination, seal/cage wear, heat balance, skidding, fits, bearing stiffness and physical durability are not established by basic fatigue arithmetic.",
            "Bearing operating temperature is an explicit input; shaft ambient temperature is not substituted. Rating capacity is assumed valid only for the declared conditions.",
            "All numerical examples are synthetic. No supplier capacity or factor table is bundled. No proprietary-standard compliance or production release is claimed."])


def bearing_report_html(result):
    esc = lambda value: html.escape(str(value))
    number = lambda value: "Unassessed" if value is None else f"{value:.9g}"
    parts = []
    for bearing in result["bearings"]:
        rows = "".join(f"<tr><td>{esc(row['name'])}</td><td>{row['rpm']:.8g}</td><td>{row['duration_hours']:.8g}</td><td>{number(row['radial_load_n'])}</td><td>{number(row['axial_load_n'])}</td><td>{number(row['equivalent_dynamic_n'])}</td><td>{number(row['equivalent_static_n'])}</td><td>{number(row['cycle_damage'])}</td><td>{number(row['static_safety'])}</td></tr>" for row in bearing["cases"])
        all_checks = [("Bearing", check) for check in bearing["checks"]] + [(row["name"], check) for row in bearing["cases"] for check in row["checks"]]
        checks = "".join(f"<tr><td>{esc(case)}</td><td>{esc(c['name'])}</td><td>{esc(c['state'])}</td><td>{esc(c['actual'])}</td><td>{esc(c['limit'])}</td><td>{esc(c['note'])}</td></tr>" for case,c in all_checks)
        parts.append(f"<h2>Bearing {bearing['position'].upper()} — {esc(bearing['designation'])}</h2><p>Assessment: {esc(bearing['assessment'])}</p>"
            f"<p>Basic per-bearing L10 under repeated duty: {number(bearing['basic_l10_repeated_duty_hours'])} h. Target damage: {number(bearing['target_damage'])}.</p>"
            f"<table><tr><th>Case</th><th>rpm</th><th>h</th><th>Fr N</th><th>Fa N</th><th>P N</th><th>P0 N</th><th>Damage</th><th>s0</th></tr>{rows}</table>"
            f"<h3>Checks</h3><table><tr><th>Case</th><th>Check</th><th>State</th><th>Value</th><th>Limit</th><th>Basis/limits</th></tr>{checks}</table>")
    return ("<!doctype html><html><head><meta charset='utf-8'><title>GearForge bearing duty</title><style>body{font-family:sans-serif;margin:24px;max-width:1400px}td,th{border:1px solid #888;padding:6px}table{border-collapse:collapse}pre{white-space:pre-wrap}</style></head><body>"
        f"<h1>{esc(result['inputs']['name'])}</h1><p><strong>Basic per-bearing fatigue arithmetic — no production gearbox rating</strong></p>"
        f"<p>GearForge {esc(result['app_version'])}; method {esc(result['method'])}. Repeated duty period {result['duty_period_hours']:.8g} h; target {result['required_hours']:.8g} h.</p>"
        + "".join(parts) + "<h2>Method limits</h2><ul>" + "".join(f"<li>{esc(item)}</li>" for item in result["limitations"]) + "</ul>"
        f"<h2>Full inputs and provenance</h2><pre>{esc(json.dumps(result['inputs'], indent=2, allow_nan=False))}</pre>"
        f"<p>Input fingerprint: {esc(result['study_sha256'])}</p><p>Shaft input fingerprint: {esc(result['shaft_study_sha256'])}</p></body></html>")


def export_bearing_study(study, destination):
    from .maintenance import write_manifest
    result = calculate_bearing_study(study);dest = Path(destination).absolute()
    if dest.exists() or dest.is_symlink():raise FileExistsError("Choose a new bearing calculation directory")
    dest.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".gearforge-bearings-", dir=dest.parent) as temporary:
        stage = Path(temporary) / "study";stage.mkdir()
        study.save(stage / "design.gearforge-bearing")
        atomic_text(stage / "calculation.json", json.dumps(result, indent=2, allow_nan=False))
        atomic_text(stage / "report.html", bearing_report_html(result))
        manifest = write_manifest(stage, kind="gearforge-bearing-study", method=METHOD,
                                  study_sha256=result["study_sha256"], production_approved=False)
        if dest.exists() or dest.is_symlink():raise FileExistsError("Bearing output directory already exists")
        stage.rename(dest)
    return dict(destination=str(dest), files=len(manifest["files"])+1, study_sha256=result["study_sha256"], production_approved=False)
