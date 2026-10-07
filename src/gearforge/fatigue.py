"""Open, bounded shaft fatigue arithmetic; no bundled material allowables.

Original implementation of the rotating-bending/steady-torque construction in
NASA RP-1123 (1984), equations 16, 19, 28-30. No published factor table is copied.
The NASA example is a numerical benchmark, never a material-selection database.
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
from .bearings import optional_number
from .engineering import _integer, _model, _text
from .models import atomic_text, finite, read_text_limited, strict_json
from .shafts import ShaftStudy, _section_stress, calculate_shaft_study

METHOD = "nasa-rp1123-rotating-shaft-1"
REFERENCE = "https://ntrs.nasa.gov/citations/19840018973"
MAX_BYTES = 3_000_000


@dataclass
class FatigueMaterial:
    designation: str = "Unspecified shaft material"
    yield_strength_mpa: float | None = None
    fatigue_coefficient_mpa: float | None = None
    reference_strength_mpa: float | None = None
    reference_cycles: float | None = None
    minimum_cycles: float | None = None
    maximum_cycles: float | None = None
    minimum_temperature_c: float | None = None
    maximum_temperature_c: float | None = None
    data_status: str = "unverified"
    source_reference: str = ""
    applicable_conditions: str = ""
    redistribution_basis: str = ""

    def validate(self):
        for key in ("designation", "source_reference", "applicable_conditions", "redistribution_basis"):
            _text(getattr(self,key), key, 4000, required=key == "designation")
        if self.data_status not in ("unverified", "synthetic", "reference_example", "declared"):
            raise ValueError("Invalid fatigue material provenance")
        for key,lo,hi in (("yield_strength_mpa",.001,100000), ("fatigue_coefficient_mpa",.001,100000),
            ("reference_strength_mpa",.001,100000), ("reference_cycles",1000,1e12),
            ("minimum_cycles",1000,1e12), ("maximum_cycles",1000,1e12), ("minimum_temperature_c",-80,200), ("maximum_temperature_c",-80,200)):
            setattr(self,key,optional_number(getattr(self,key),key,lo,hi))
        for low,high in ((self.reference_strength_mpa,self.fatigue_coefficient_mpa),
                         (self.minimum_cycles,self.reference_cycles), (self.minimum_cycles,self.maximum_cycles)):
            if low is not None and high is not None and low >= high:
                raise ValueError("Fatigue endpoints require reference strength below coefficient and minimum cycles below reference cycles")
        if self.reference_cycles is not None and self.maximum_cycles is not None and self.maximum_cycles < self.reference_cycles:
            raise ValueError("Maximum supported cycles must include the reference cycle anchor")
        if self.minimum_temperature_c is not None and self.maximum_temperature_c is not None and self.minimum_temperature_c > self.maximum_temperature_c:
            raise ValueError("Material temperature limits are reversed")


@dataclass
class FatigueStation:
    name: str = "Critical section"
    position_mm: float = 60.0
    side: str = "left"
    fatigue_reduction_factor: float | None = None
    static_bending_kt: float | None = None
    static_torsion_kt: float | None = None
    static_axial_kt: float | None = None
    factor_basis: str = ""

    def validate(self,length):
        _text(self.name,"Critical section name",120,required=True)
        _text(self.factor_basis,"Section factor basis",4000)
        self.position_mm=finite(self.position_mm,"Critical section position",0,length)
        if self.side not in ("left","right") or (self.position_mm == 0 and self.side == "left") or (self.position_mm == length and self.side == "right"):
            raise ValueError("Critical section side must lie inside the shaft")
        self.fatigue_reduction_factor=optional_number(self.fatigue_reduction_factor,"Fatigue reduction factor",.000001,1)
        for key in ("static_bending_kt","static_torsion_kt","static_axial_kt"):
            setattr(self,key,optional_number(getattr(self,key),key,1,100))


@dataclass
class FatigueCase:
    case_name: str = "Operating load"
    load_model: str = "unverified"
    operating_temperature_c: float | None = None
    basis: str = ""

    def validate(self):
        _text(self.case_name,"Fatigue case name",120,required=True)
        _text(self.basis,"Load model basis",4000)
        if self.load_model not in ("unverified","fixed_bending_steady_torque","other"):
            raise ValueError("Invalid fatigue load model")
        self.operating_temperature_c=optional_number(self.operating_temperature_c,"Shaft operating temperature",-80,200)


@dataclass
class FatigueStudy:
    name: str = "Shaft fatigue study"
    shaft: ShaftStudy = field(default_factory=ShaftStudy)
    material: FatigueMaterial = field(default_factory=FatigueMaterial)
    stations: list[FatigueStation] = field(default_factory=lambda:[FatigueStation()])
    cases: list[FatigueCase] = field(default_factory=lambda:[FatigueCase()])
    bending_design_factor: float = 1.0
    static_design_factor: float = 1.0
    required_hours: float = 10000.0
    duty_coverage_basis: str = ""
    notes: str = "Rotation blocks only. Assess starts, stops, reversals, load transitions and all other critical sections separately."
    schema_version: int = 1

    def validate(self):
        _integer(self.schema_version,"Fatigue schema",1,1)
        _text(self.name,"Fatigue study name",1000,required=True)
        _text(self.duty_coverage_basis,"Duty coverage basis",10000)
        _text(self.notes,"Fatigue notes",10000)
        if not isinstance(self.shaft,ShaftStudy) or not isinstance(self.material,FatigueMaterial):raise ValueError("Shaft and material inputs are required")
        self.shaft.validate();self.material.validate()
        for key in ("bending_design_factor","static_design_factor"):
            setattr(self,key,finite(getattr(self,key),key,1,100))
        self.required_hours=finite(self.required_hours,"Required hours",.000001,2e8)
        if not isinstance(self.stations,list) or not 1 <= len(self.stations) <= 50:raise ValueError("Define 1..50 critical sections")
        for station in self.stations:
            if not isinstance(station,FatigueStation):raise ValueError("Invalid fatigue section")
            station.validate(self.shaft.length_mm)
        if len({s.name for s in self.stations}) != len(self.stations):raise ValueError("Critical section names must be unique")
        if not isinstance(self.cases,list) or len(self.cases) != len(self.shaft.cases):raise ValueError("Every shaft case requires fatigue conditions")
        for case in self.cases:
            if not isinstance(case,FatigueCase):raise ValueError("Invalid fatigue case")
            case.validate()
        if {c.case_name for c in self.cases} != {c.name for c in self.shaft.cases}:raise ValueError("Fatigue cases must match retained shaft cases exactly")

    @classmethod
    def from_dict(cls,data):
        if not isinstance(data,dict):raise ValueError("Invalid fatigue study")
        data=dict(data)
        for key,limit in (("stations",50),("cases",200)):
            if not isinstance(data.get(key),list) or len(data[key]) > limit:raise ValueError("Missing or excessive fatigue inputs")
        data["shaft"]=ShaftStudy.from_dict(data.get("shaft"))
        data["material"]=_model(FatigueMaterial,data.get("material"))
        data["stations"]=[_model(FatigueStation,row) for row in data["stations"]]
        data["cases"]=[_model(FatigueCase,row) for row in data["cases"]]
        result=_model(cls,data);result.validate();return result

    @classmethod
    def load(cls,path):return cls.from_dict(strict_json(read_text_limited(Path(path),MAX_BYTES,"Fatigue study")))

    def save(self,path):
        self.validate();text=json.dumps(asdict(self),indent=2,allow_nan=False)
        if len(text.encode("utf-8")) > MAX_BYTES:raise ValueError("Fatigue study exceeds 3 MB")
        atomic_text(Path(path),text)


def fatigue_from_shaft(shaft: ShaftStudy) -> FatigueStudy:
    shaft=ShaftStudy.from_dict(asdict(shaft))
    return FatigueStudy(name=f"{shaft.name} — fatigue",shaft=shaft,
        stations=[FatigueStation(position_mm=shaft.length_mm/2)],
        cases=[FatigueCase(case_name=c.name) for c in shaft.cases],
        required_hours=math.fsum(c.duration_hours for c in shaft.cases))


def stress_life_block(material: FatigueMaterial, station: FatigueStation, bending_mpa: float,
                      torsion_mpa: float, cycles: float, bending_factor=1.0) -> dict:
    """Validated numerical kernel, separate from provenance and load-path checks.

    NASA's steady-torque ellipse reduces the reference fatigue endpoint. The
    one-cycle coefficient stays fixed. No extrapolation below/above the declared
    finite-life interval, no infinite-life assertion, no automatic mean axial term.
    """
    result=dict(corrected_reference_strength_mpa=None,exponent=None,cycles_to_failure=None,damage=None,range_state="missing_data")
    if any(v is None for v in (material.yield_strength_mpa,material.fatigue_coefficient_mpa,
        material.reference_strength_mpa,material.reference_cycles,material.minimum_cycles,material.maximum_cycles,station.fatigue_reduction_factor)):
        return result
    ellipse=1-3*(torsion_mpa/material.yield_strength_mpa)**2
    if ellipse <= 0:return dict(result,range_state="mean_torque_exceeds_ellipse")
    endpoint=material.reference_strength_mpa*station.fatigue_reduction_factor*math.sqrt(ellipse)
    exponent=math.log(material.fatigue_coefficient_mpa/endpoint)/math.log(material.reference_cycles)
    result.update(corrected_reference_strength_mpa=endpoint,exponent=exponent)
    amplitude=bending_factor*bending_mpa
    if cycles == 0:return dict(result,damage=0.0,range_state="stationary_no_rotation_cycles")
    if amplitude == 0:return dict(result,damage=0.0,range_state="zero_rotating_bending")
    log_life=(math.log(material.fatigue_coefficient_mpa)-math.log(amplitude))/exponent
    # Endpoint roundoff must not turn an exact boundary into extrapolation.
    if log_life > math.log(material.maximum_cycles)+1e-12:return dict(result,range_state="beyond_maximum_cycles")
    if log_life < math.log(material.minimum_cycles)-1e-12:return dict(result,range_state="below_minimum_cycles")
    life=min(material.maximum_cycles,max(material.minimum_cycles,math.exp(log_life)))
    return dict(result,cycles_to_failure=life,damage=cycles/life,range_state="within_declared_cycle_range")


def nasa_example() -> FatigueStudy:
    """Original load-path representation of the public RP-1123 example, pp18-19.

    The 600 mm span is a fixture choice; each center moment equals NASA's input.
    Static Kt=1 and the temperature interval are synthetic adapter assumptions.
    Material numbers are historical example inputs, not design allowables.
    """
    from .shafts import ShaftCase,ShaftLoad,ShaftSection
    shaft=ShaftStudy(name="NASA RP-1123 numerical example load path",length_mm=600,bearing_b_mm=600,
        sections=[ShaftSection(end_mm=600,outer_diameter_mm=55)],cases=[
            ShaftCase(name=f"Moment {moment} N m",rpm=1000,duration_hours=count/60000,
                loads=[ShaftLoad(name="Center load",position_mm=300,force_y_n=-moment*1000/150,torque_nm=-3000),
                       ShaftLoad(name="Drive",position_mm=0,torque_nm=3000)])
            for moment,count in ((2000,15000),(1500,35000),(1000,50000))],
        source_description="NASA RP-1123 pp18-19 numerical inputs; original simply supported load-path adapter",
        notes="Historical numerical benchmark only. 600 mm span and 1000 rpm are adapter choices, not NASA geometry or operating data.")
    study=fatigue_from_shaft(shaft);study.name="NASA shaft fatigue worked example — not material allowables"
    study.material=FatigueMaterial(designation="Historical RP-1123 example inputs; not a purchasable material specification",
        yield_strength_mpa=634,fatigue_coefficient_mpa=1227,reference_strength_mpa=323,
        reference_cycles=1e6,minimum_cycles=1000,maximum_cycles=1e7,minimum_temperature_c=20,maximum_temperature_c=40,
        data_status="reference_example",source_reference=REFERENCE+"; printed pp17-19, equations 28-31",
        applicable_conditions="Historical example only. Temperature window and 1e3..1e7 cycle window are numerical adapter assumptions, not validated material limits; no population survival claim.",
        redistribution_basis="NTRS marks this NASA-authored work: Work of the US Gov. Public Use Permitted. Original adapter: Apache-2.0.")
    study.stations=[FatigueStation(name="Center, drive side",position_mm=300,side="left",fatigue_reduction_factor=.4,
        static_bending_kt=1,static_torsion_kt=1,static_axial_kt=1,
        factor_basis="NASA example assumes total fatigue reduction 0.4; unit static factors are synthetic adapter inputs.")]
    study.cases=[FatigueCase(case_name=c.name,load_model="fixed_bending_steady_torque",operating_temperature_c=25,
        basis="Original adapter: fixed transverse center force and steady torque during each rotation block") for c in shaft.cases]
    study.bending_design_factor=2;study.static_design_factor=1
    study.duty_coverage_basis="NASA three-level bending spectrum, constant 3000 N m torque. Transient paths and physical fatigue tests are not supplied."
    study.validate();return study


def calculate_fatigue_study(study: FatigueStudy) -> dict:
    study.validate();shaft=calculate_shaft_study(study.shaft);material=study.material
    conditions={c.case_name:c for c in study.cases};results=[]
    for station in study.stations:
        checks=[];rows=[]
        def check(name,passed,note):
            checks.append(dict(name=name,state="unassessed" if passed is None else "within_limit" if passed else "outside_limit",note=note))
        declared=material.data_status=="declared" and all(t.strip() for t in
            (material.source_reference,material.applicable_conditions,material.redistribution_basis))
        check("Material provenance",True if declared else None,"Entered evidence requires independent review; example numbers are never material allowables.")
        check("Section factor evidence",True if station.factor_basis.strip() else None,"The fatigue product includes surface, size, notch, environment and survival basis. Elastic static factors are separate.")
        for index,case in enumerate(study.shaft.cases):
            condition=conditions[case.name];stress=_section_stress(study.shaft,case,station.position_mm,station.side)
            issues=[];temperature=condition.operating_temperature_c
            supported=condition.load_model=="fixed_bending_steady_torque" and bool(condition.basis.strip())
            if not supported:issues.append("Confirm fixed-in-housing bending and steady within-block torque; rotating loads and oscillation are unsupported.")
            if stress["axial_force_n"] != 0:
                supported=False;issues.append("Axial load is present at this cut; this fatigue method has no mean/alternating axial correction.")
            if stress["section"]["inner_diameter_mm"] != 0:
                supported=False;issues.append("The validated fatigue scope is a solid circular shaft; hollow-section fatigue is unassessed.")
            check(f"{case.name}: shaft load model",True if supported and not shaft["cases"][index]["findings"] else None,
                  " ".join(issues+shaft["cases"][index]["findings"]) or "Explicit rotating-bending/steady-torque model.")
            temperature_known=all(v is not None for v in (temperature,material.minimum_temperature_c,material.maximum_temperature_c))
            check(f"{case.name}: material operating temperature",None if not temperature_known else material.minimum_temperature_c <= temperature <= material.maximum_temperature_c,
                  "Use shaft operating temperature and material evidence; ambient temperature is not substituted.")
            factors=(station.static_bending_kt,station.static_torsion_kt,station.static_axial_kt)
            equivalent=None if any(v is None for v in factors) else math.hypot(
                factors[0]*stress["nominal_bending_mpa"]+factors[2]*abs(stress["nominal_axial_mpa"]),
                math.sqrt(3)*factors[1]*stress["nominal_torsion_mpa"])
            static_ok=None if equivalent is None or material.yield_strength_mpa is None else study.static_design_factor*equivalent <= material.yield_strength_mpa
            check(f"{case.name}: elastic surface yield",static_ok,"Static design factor multiplies local elastic von Mises surface stress; transverse shear, local plasticity and buckling are excluded.")
            cycles=60*abs(case.rpm)*case.duration_hours
            block=stress_life_block(material,station,stress["nominal_bending_mpa"],stress["nominal_torsion_mpa"],cycles,study.bending_design_factor) if supported else dict(
                corrected_reference_strength_mpa=None,exponent=None,cycles_to_failure=None,damage=None,range_state="unsupported_load_path")
            # Plastic response invalidates the elastic stress-life calculation.
            if equivalent is not None and material.yield_strength_mpa is not None and equivalent >= material.yield_strength_mpa:
                block.update(cycles_to_failure=None,damage=None,range_state="elastic_yield_reached")
            if temperature_known and not material.minimum_temperature_c <= temperature <= material.maximum_temperature_c:
                block.update(cycles_to_failure=None,damage=None,range_state="outside_material_temperature")
            check(f"{case.name}: finite-life range",True if block["damage"] is not None else None,
                  block["range_state"].replace("_"," ")+". No S–N extrapolation or infinite-life assumption.")
            rows.append(dict(name=case.name,rpm=case.rpm,duration_hours=case.duration_hours,rotation_cycles=cycles,
                stress=stress,local_static_von_mises_mpa=equivalent,**block))
        damage=math.fsum(r["damage"] for r in rows) if all(r["damage"] is not None for r in rows) else None
        target=None if damage is None else damage*study.required_hours/shaft["total_hours"]
        check("Modeled rotation-block damage at target",None if target is None else target <= 1,"Miner sum over modeled rotation blocks only; omitted transients cannot be counted as zero damage.")
        # Coverage cannot be self-certified by a text field. These remain studies.
        check("Duty and critical-section coverage",None,"Starts, stops, transitions, torsional cycles and all critical sections require separate assessment. Duty notes are provenance, not a coverage approval.")
        state="outside_entered_limits" if any(c["state"]=="outside_limit" for c in checks) else "incomplete"
        if material.data_status in ("synthetic","reference_example"):state="example_outside_entered_limits" if state=="outside_entered_limits" else "example_only"
        results.append(dict(name=station.name,position_mm=station.position_mm,side=station.side,assessment=state,
            cases=rows,checks=checks,modeled_block_damage=damage,target_modeled_block_damage=target))
    inputs=asdict(study);digest=hashlib.sha256(json.dumps(inputs,sort_keys=True,separators=(",",":"),allow_nan=False).encode()).hexdigest()
    return dict(schema_version=1,app_version=__version__,method=METHOD,method_reference=REFERENCE,inputs=inputs,
        study_sha256=digest,shaft_study_sha256=shaft["study_sha256"],duty_period_hours=shaft["total_hours"],stations=results,
        production_approved=False,rated_gearbox_life_hours=None,limitations=[
            "Solid circular metallic shaft, elastic high-cycle rotating bending and steady within-block torque. No automatic material strength from a name.",
            "NASA RP-1123 ellipse reduces the reference fatigue endpoint using nominal steady torsion; the one-cycle coefficient stays fixed. Fatigue reduction factors are explicit user inputs.",
            "Bending design factor multiplies alternating bending demand only; static design factor multiplies local elastic stress. Neither is a survival probability.",
            "Only the declared finite-life interval is used. Lower stresses do not establish infinite life; low-cycle plasticity and axial/hollow fatigue are unassessed.",
            "Miner damage ignores sequence effects. Revolution counts do not count startup, shutdown, torsional reversal, vibration or transition fatigue cycles.",
            "Only selected cuts are assessed. Shoulders, keyways, fits, surface, residual stress, temperature, corrosion, material scatter and manufacturing evidence require applicable factors and review.",
            "Material and load declarations are not independent validation. A stored reference or synthetic example is never a supplier material selection.",
            "Modeled rotation-block damage is not shaft service life or a gearbox production rating."])


def fatigue_report_html(result):
    esc=lambda v:html.escape(str(v))
    def fmt(value):return "Unassessed" if value is None else f"{value:.8g}"
    parts=[]
    for station in result["stations"]:
        rows="".join(f"<tr><td>{esc(r['name'])}</td><td>{fmt(r['rotation_cycles'])}</td><td>{fmt(r['stress']['nominal_bending_mpa'])}</td><td>{fmt(r['stress']['nominal_torsion_mpa'])}</td><td>{fmt(r['cycles_to_failure'])}</td><td>{fmt(r['damage'])}</td><td>{esc(r['range_state'].replace('_',' '))}</td></tr>" for r in station["cases"])
        checks="".join(f"<li><strong>{esc(c['name'])}: {esc(c['state'].replace('_',' '))}.</strong> {esc(c['note'])}</li>" for c in station["checks"])
        parts.append(f"<h2>{esc(station['name'])} — {esc(station['assessment'].replace('_',' '))}</h2><p>X={station['position_mm']:.8g} mm, {esc(station['side'])} cut. Target rotation-block damage: {fmt(station['target_modeled_block_damage'])}.</p>"
            f"<table><tr><th>Case</th><th>Rotation cycles</th><th>Bending MPa</th><th>Torque shear MPa</th><th>Model failure cycles</th><th>Block damage</th><th>Range</th></tr>{rows}</table><ul>{checks}</ul>")
    limits="".join(f"<li>{esc(s)}</li>" for s in result["limitations"])
    return ("<!doctype html><html><head><meta charset='utf-8'><title>Shaft fatigue study</title><style>body{font-family:Arial,sans-serif;margin:24px;max-width:1250px}table{border-collapse:collapse}td,th{border:1px solid #888;padding:6px}pre{white-space:pre-wrap}</style></head><body>"
        f"<h1>{esc(result['inputs']['name'])}</h1><p><strong>Modeled rotation blocks — no production or gearbox service-life rating</strong></p>"
        f"<p>GearForge {esc(result['app_version'])}; method {esc(result['method'])}. <a href='{REFERENCE}'>NASA RP-1123 method reference</a>.</p>"
        +"".join(parts)+f"<h2>Method limits</h2><ul>{limits}</ul><h2>Complete inputs and evidence</h2><pre>{esc(json.dumps(result['inputs'],indent=2,allow_nan=False))}</pre><p>Input fingerprint: {esc(result['study_sha256'])}</p></body></html>")


def export_fatigue_study(study,destination):
    from .maintenance import write_manifest
    result=calculate_fatigue_study(study);dest=Path(destination).absolute()
    if dest.exists() or dest.is_symlink():raise FileExistsError("Choose a new fatigue assessment directory")
    dest.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".gearforge-fatigue-",dir=dest.parent) as temporary:
        stage=Path(temporary)/"study";stage.mkdir()
        study.save(stage/"design.gearforge-fatigue")
        atomic_text(stage/"calculation.json",json.dumps(result,indent=2,allow_nan=False))
        atomic_text(stage/"report.html",fatigue_report_html(result))
        manifest=write_manifest(stage,kind="gearforge-fatigue-study",method=METHOD,study_sha256=result["study_sha256"],production_approved=False)
        if dest.exists() or dest.is_symlink():raise FileExistsError("Fatigue output directory already exists")
        stage.rename(dest)
    return dict(destination=str(dest),files=len(manifest["files"])+1,study_sha256=result["study_sha256"],production_approved=False)
