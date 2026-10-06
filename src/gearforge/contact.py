"""Original external-spur Hertz line-contact and declared pressure-life studies.

The mesh carries load through ideal involute geometry. Load sharing is an
explicit envelope or ideal equal-pair assumption, not a stiffness solution.
No material/factor table, production allowable or standards text is bundled.
"""
from __future__ import annotations

from dataclasses import asdict,dataclass,field
import hashlib
import html
import json
import math
from pathlib import Path
import tempfile

from . import __version__
from .bearings import optional_number
from .engineering import EngineeringStudy,_integer,_model,_text,calculate_study
from .models import atomic_text,finite,read_text_limited,strict_json

METHOD="external-spur-line-contact-1"
MAX_BYTES=3_000_000


@dataclass
class ContactLifePoint:
    cycles: float = 1000000.0
    pressure_mpa: float = 500.0

    def validate(self):
        self.cycles=finite(self.cycles,"Contact fatigue cycles",1,1e15)
        self.pressure_mpa=finite(self.pressure_mpa,"Contact fatigue pressure",.001,100000)


@dataclass
class ContactMaterial:
    role: str = "pinion"
    designation: str = "Unspecified gear material and surface condition"
    youngs_modulus_mpa: float | None = None
    poisson_ratio: float | None = None
    maximum_elastic_pressure_mpa: float | None = None
    minimum_temperature_c: float | None = None
    maximum_temperature_c: float | None = None
    life_curve: list[ContactLifePoint] = field(default_factory=list)
    data_status: str = "unverified"
    source_reference: str = ""
    applicable_conditions: str = ""
    redistribution_basis: str = ""

    def validate(self):
        if self.role not in ("pinion","wheel") or self.data_status not in ("unverified","synthetic","declared"):
            raise ValueError("Invalid contact material role or provenance")
        for key in ("designation","source_reference","applicable_conditions","redistribution_basis"):
            _text(getattr(self,key),key,4000,required=key=="designation")
        for key,lo,hi in (("youngs_modulus_mpa",1,1e6),("poisson_ratio",0,.49),
            ("maximum_elastic_pressure_mpa",.001,100000),("minimum_temperature_c",-80,200),("maximum_temperature_c",-80,200)):
            setattr(self,key,optional_number(getattr(self,key),key,lo,hi))
        if self.minimum_temperature_c is not None and self.maximum_temperature_c is not None and self.minimum_temperature_c>self.maximum_temperature_c:
            raise ValueError("Contact material temperatures are reversed")
        if not isinstance(self.life_curve,list) or len(self.life_curve)>50 or len(self.life_curve)==1:
            raise ValueError("Contact life curve requires zero or 2..50 points")
        for point in self.life_curve:
            if not isinstance(point,ContactLifePoint):raise ValueError("Invalid pressure-life point")
            point.validate()
        for a,b in zip(self.life_curve,self.life_curve[1:]):
            if a.cycles>=b.cycles or a.pressure_mpa<=b.pressure_mpa:
                raise ValueError("Life-curve cycles must strictly increase while pressures strictly decrease")


@dataclass
class ContactCase:
    case_name: str = "Continuous rated-input target"
    normal_load_multiplier: float | None = None
    face_line_load_multiplier: float | None = None
    effective_face_width_mm: float | None = None
    pinion_temperature_c: float | None = None
    wheel_temperature_c: float | None = None
    factor_basis: str = ""

    def validate(self,width):
        _text(self.case_name,"Contact duty name",120,required=True)
        _text(self.factor_basis,"Contact factor basis",4000)
        for key,lo,hi in (("normal_load_multiplier",1,100),("face_line_load_multiplier",1,100),
            ("effective_face_width_mm",.001,width),("pinion_temperature_c",-80,200),("wheel_temperature_c",-80,200)):
            setattr(self,key,optional_number(getattr(self,key),key,lo,hi))


@dataclass
class ContactStudy:
    name: str = "Tooth contact and pressure-life study"
    source: EngineeringStudy = field(default_factory=EngineeringStudy)
    materials: list[ContactMaterial] = field(default_factory=lambda:[ContactMaterial(),ContactMaterial(role="wheel")])
    cases: list[ContactCase] = field(default_factory=lambda:[ContactCase()])
    load_sharing: str = "full_load_envelope"
    pressure_design_factor: float = 1.0
    load_sharing_basis: str = ""
    notes: str = "Ideal spur geometry and frictionless elastic line contact. Establish actual load distribution, material/surface and lubrication evidence before engineering release."
    schema_version: int = 1

    def validate(self):
        _integer(self.schema_version,"Contact schema",1,1)
        _text(self.name,"Contact study name",1000,required=True)
        _text(self.notes,"Contact notes",10000);_text(self.load_sharing_basis,"Load-sharing basis",4000)
        if not isinstance(self.source,EngineeringStudy):raise ValueError("Retained gear study is required")
        self.source.validate()
        self.pressure_design_factor=finite(self.pressure_design_factor,"Pressure design factor",1,100)
        if self.load_sharing not in ("full_load_envelope","equal_pairs"):
            raise ValueError("Choose full mesh-load envelope or ideal equal-pair sharing")
        if not isinstance(self.materials,list) or len(self.materials)!=2:raise ValueError("Define both gear materials")
        for material in self.materials:
            if not isinstance(material,ContactMaterial):raise ValueError("Invalid contact material")
            material.validate()
        if {m.role for m in self.materials}!={"pinion","wheel"}:raise ValueError("Define pinion and wheel material once each")
        if not isinstance(self.cases,list) or len(self.cases)!=len(self.source.duty):raise ValueError("Every gear duty case requires contact conditions")
        for case in self.cases:
            if not isinstance(case,ContactCase):raise ValueError("Invalid contact conditions")
            case.validate(self.source.pair.face_width_mm)
        if {c.case_name for c in self.cases}!={c.name for c in self.source.duty}:raise ValueError("Contact cases must match every retained duty case")

    @classmethod
    def from_dict(cls,data):
        if not isinstance(data,dict):raise ValueError("Invalid contact study")
        data=dict(data)
        if not isinstance(data.get("materials"),list) or len(data["materials"])!=2:raise ValueError("Missing contact materials")
        if not isinstance(data.get("cases"),list) or len(data["cases"])>200:raise ValueError("Missing or excessive contact cases")
        materials=[]
        for row in data["materials"]:
            if not isinstance(row,dict) or not isinstance(row.get("life_curve"),list) or len(row["life_curve"])>50:
                raise ValueError("Invalid contact life curve")
            row=dict(row);row["life_curve"]=[_model(ContactLifePoint,p) for p in row["life_curve"]]
            materials.append(_model(ContactMaterial,row))
        data["source"]=EngineeringStudy.from_dict(data.get("source"));data["materials"]=materials
        data["cases"]=[_model(ContactCase,row) for row in data["cases"]]
        result=_model(cls,data);result.validate();return result

    @classmethod
    def load(cls,path):return cls.from_dict(strict_json(read_text_limited(Path(path),MAX_BYTES,"Contact study")))

    def save(self,path):
        self.validate();text=json.dumps(asdict(self),indent=2,allow_nan=False)
        if len(text.encode("utf-8"))>MAX_BYTES:raise ValueError("Contact study exceeds 3 MB")
        atomic_text(Path(path),text)


def contact_from_study(source):
    source=EngineeringStudy.from_dict(asdict(source))
    return ContactStudy(name=f"{source.name} — tooth contact",source=source,
        cases=[ContactCase(case_name=c.name) for c in source.duty])


def synthetic_contact_example():
    study=contact_from_study(EngineeringStudy());study.name="Synthetic tooth-contact example — no material allowables"
    study.load_sharing_basis="Full mesh force applied to each examined pair as a local envelope; original arithmetic fixture. No measured stiffness or contact pattern."
    for m in study.materials:
        m.designation="Invented isotropic metal contact fixture";m.youngs_modulus_mpa=210000;m.poisson_ratio=.3
        m.maximum_elastic_pressure_mpa=1500;m.minimum_temperature_c=20;m.maximum_temperature_c=80
        m.life_curve=[ContactLifePoint(1000,900),ContactLifePoint(1e10,100)]
        m.data_status="synthetic";m.source_reference="Original GearForge numerical fixture; no supplier or measured material data"
        m.applicable_conditions="Invented modulus, elastic-pressure limit and pressure-life points; no physical pitting, surface, lubricant or reliability qualification"
        m.redistribution_basis="Original GearForge fixture, Apache-2.0"
    for c in study.cases:
        c.normal_load_multiplier=1;c.face_line_load_multiplier=1;c.effective_face_width_mm=20
        c.pinion_temperature_c=c.wheel_temperature_c=40
        c.factor_basis="Synthetic uniform-width quasi-static fixture; unity multipliers are not verified dynamic/alignment factors"
    return study


def hertz_line(radius1_mm,radius2_mm,line_load_n_per_mm,e1_mpa,e2_mpa,nu1,nu2):
    """Frictionless line contact, positive convex local radii, MPa=N/mm²."""
    r1=finite(radius1_mm,"First curvature radius",1e-12,1e9)
    r2=finite(radius2_mm,"Second curvature radius",1e-12,1e9)
    w=finite(line_load_n_per_mm,"Line load",0,1e20)
    e1=finite(e1_mpa,"First elastic modulus",1,1e6);e2=finite(e2_mpa,"Second elastic modulus",1,1e6)
    v1=finite(nu1,"First Poisson ratio",0,.49);v2=finite(nu2,"Second Poisson ratio",0,.49)
    radius=r1*r2/(r1+r2);modulus=1/((1-v1*v1)/e1+(1-v2*v2)/e2)
    return dict(effective_radius_mm=radius,effective_modulus_mpa=modulus,
        half_width_mm=math.sqrt(4*w*radius/(math.pi*modulus)),
        peak_pressure_mpa=math.sqrt(w*modulus/(math.pi*radius)))


def _mesh_path(geometry,sharing):
    """Exact contact-count intervals and their one-sided critical limits.

    On each interval p0² is proportional to 1/(rho1*rho2), with rho1+rho2
    constant. Thus maximum pressure is at an endpoint, never a grid maximum.
    """
    g=geometry;alpha=math.radians(g["operating_pressure_angle_deg"])
    tangent=g["operating_center_distance_mm"]*math.sin(alpha)
    roll1=math.sqrt(g["pinion"]["tip_diameter_mm"]**2-g["pinion"]["base_diameter_mm"]**2)/2
    roll2=math.sqrt(g["wheel"]["tip_diameter_mm"]**2-g["wheel"]["base_diameter_mm"]**2)/2
    first=tangent-roll2;length=roll1-first;pitch=g["transverse_base_pitch_mm"]
    if first<=0 or tangent-roll1<=0:raise ValueError("Contact reaches a base-circle singularity; generated-profile analysis is required")
    limits={0.,length}
    for i in range(1,math.ceil(length/pitch)+1):
        for value in (i*pitch,length-i*pitch):
            if 1e-10 < value < length-1e-10:limits.add(value)
    limits=sorted(limits);nodes=[];intervals=[]
    pitch_position=g["pinion"]["operating_pitch_diameter_mm"]/2*math.sin(alpha)-first
    for start,end in zip(limits,limits[1:]):
        middle=(start+end)/2
        count=math.floor((length-middle)/pitch)-math.ceil(-middle/pitch)+1
        fraction=1.0 if sharing=="full_load_envelope" else 1/count
        intervals.append(dict(start_mm=start,end_mm=end,simultaneous_pairs=count,pair_load_fraction=fraction))
        positions={start:"right",end:"left"}
        for p in (pitch_position,tangent/2-first):
            if start<p<end:positions[p]="interior"
        # Samples draw the curve; endpoint records establish continuous maxima.
        for i in range(1,41):
            p=start+(end-start)*i/41
            if p not in positions:positions[p]="sample"
        for p,side in sorted(positions.items()):
            rho1=first+p;rho2=tangent-rho1
            nodes.append(dict(path_mm=p,relative_to_pitch_mm=p-pitch_position,side=side,
                critical=side!="sample",pinion_curvature_mm=rho1,wheel_curvature_mm=rho2,
                simultaneous_pairs=count,pair_load_fraction=fraction))
    return dict(length_mm=length,pitch_position_mm=pitch_position,intervals=intervals,nodes=nodes)


def contact_life(curve,pressure):
    """Log-log interpolation only within declared empirical pressure-life data."""
    if not curve:return dict(cycles_to_failure=None,state="missing_pressure_life_curve")
    if pressure==0:return dict(cycles_to_failure=None,state="zero_pressure")
    if pressure>curve[0].pressure_mpa*(1+1e-12):return dict(cycles_to_failure=None,state="above_curve_pressure")
    if pressure<curve[-1].pressure_mpa*(1-1e-12):return dict(cycles_to_failure=None,state="below_curve_pressure")
    pressure=min(curve[0].pressure_mpa,max(curve[-1].pressure_mpa,pressure))
    for a,b in zip(curve,curve[1:]):
        if b.pressure_mpa<=pressure<=a.pressure_mpa:
            fraction=math.log(pressure/a.pressure_mpa)/math.log(b.pressure_mpa/a.pressure_mpa)
            return dict(cycles_to_failure=math.exp(math.log(a.cycles)+fraction*math.log(b.cycles/a.cycles)),state="within_declared_curve")
    raise ValueError("Invalid pressure-life interpolation interval")


def calculate_contact_study(study):
    study.validate();source=calculate_study(study.source);g=source["geometry"]
    findings=list(g["issues"])
    if study.source.pair.pinion_helix_angle_deg!=0:findings.append("Helical line orientation, overlap and contact distribution require a separate model; this study supports external spur gears only.")
    path=None
    if not findings:
        try:path=_mesh_path(g,study.load_sharing)
        except ValueError as exc:findings.append(str(exc))
    materials={m.role:m for m in study.materials};conditions={c.case_name:c for c in study.cases}
    m1,m2=materials["pinion"],materials["wheel"]
    elastic_known=all(x is not None for x in (m1.youngs_modulus_mpa,m2.youngs_modulus_mpa,m1.poisson_ratio,m2.poisson_ratio))
    rows=[]
    for duty in source["duty_results"]:
        condition=conditions[duty["name"]];checks=[]
        def check(name,passed,note):
            checks.append(dict(name=name,state="unassessed" if passed is None else "within_limit" if passed else "outside_limit",note=note))
        factors_known=all(x is not None for x in (condition.normal_load_multiplier,condition.face_line_load_multiplier,condition.effective_face_width_mm))
        check("Load-factor evidence",True if condition.factor_basis.strip() and factors_known else None,
            "Normal multiplier covers declared application/dynamic load; face multiplier represents peak line-load concentration. No factors are inferred.")
        check("Elastic constants",True if elastic_known else None,"Both materials require isotropic elastic moduli and Poisson ratios at the declared conditions.")
        profile=[];hertz_domain=True
        if path is not None and factors_known and elastic_known:
            omega=abs(duty["input_rpm"])*2*math.pi/60
            for node in path["nodes"]:
                line_load=duty["normal_force_magnitude_n"]*condition.normal_load_multiplier*condition.face_line_load_multiplier*node["pair_load_fraction"]/condition.effective_face_width_mm
                hertz=hertz_line(node["pinion_curvature_mm"],node["wheel_curvature_mm"],line_load,
                    m1.youngs_modulus_mpa,m2.youngs_modulus_mpa,m1.poisson_ratio,m2.poisson_ratio)
                v1=omega*node["pinion_curvature_mm"]/1000;v2=omega/g["ratio"]*node["wheel_curvature_mm"]/1000
                domain=hertz["half_width_mm"]<=.05*min(node["pinion_curvature_mm"],node["wheel_curvature_mm"],condition.effective_face_width_mm)
                hertz_domain=hertz_domain and domain
                profile.append(dict(**node,**hertz,line_load_n_per_mm=line_load,within_small_contact_guard=domain,
                    pinion_surface_speed_m_s=v1,wheel_surface_speed_m_s=v2,sliding_speed_m_s=abs(v1-v2),
                    slide_roll_ratio=None if v1+v2==0 else 2*(v1-v2)/(v1+v2)))
        critical=[p for p in profile if p["critical"]]
        worst=max(critical,key=lambda p:p["peak_pressure_mpa"]) if critical else None
        check("Small-contact model guard",None if not profile else hertz_domain,
            "Contact half-width must be ≤5% of both curvature radii and effective face width. This development guard is not proof of elastic or edge-contact validity.")
        pressures=None if worst is None else study.pressure_design_factor*worst["peak_pressure_mpa"]
        member_rows=[]
        for role,material in materials.items():
            temp=getattr(condition,f"{role}_temperature_c")
            temp_known=all(x is not None for x in (temp,material.minimum_temperature_c,material.maximum_temperature_c))
            temp_ok=None if not temp_known else material.minimum_temperature_c<=temp<=material.maximum_temperature_c
            check(f"{role}: operating temperature",temp_ok,"Gear operating temperature is separate from the retained ambient temperature.")
            elastic_ok=None if pressures is None or material.maximum_elastic_pressure_mpa is None else pressures<=material.maximum_elastic_pressure_mpa
            check(f"{role}: declared elastic-pressure limit",elastic_ok,"Pressure design factor multiplies peak Hertz pressure; this is not a yield-strength conversion or a load factor.")
            exposure=duty[f"{role}_revolutions"]
            life=dict(cycles_to_failure=None,state="contact_model_unavailable") if pressures is None else contact_life(material.life_curve,pressures)
            damage=None
            if pressures is not None and hertz_domain and temp_ok is not False and elastic_ok is not False:
                if exposure==0 or pressures==0:
                    damage=0.0;life=dict(cycles_to_failure=None,state="no_loaded_rotation_cycles")
                elif life["cycles_to_failure"] is not None:damage=exposure/life["cycles_to_failure"]
            else:life=dict(cycles_to_failure=None,state="contact_domain_or_conditions_unassessed")
            check(f"{role}: pressure-life range",True if damage is not None else None,life["state"].replace("_"," ")+". No curve extrapolation or infinite-life claim.")
            member_rows.append(dict(role=role,tooth_contact_cycles=exposure,cycles_to_failure=life["cycles_to_failure"],
                curve_state=life["state"],modeled_flank_damage=damage))
        torque=duty["input_torque_nm"];flank="positive_torque" if torque>0 else "negative_torque" if torque<0 else "unloaded"
        rows.append(dict(name=duty["name"],input_rpm=duty["input_rpm"],duration_hours=duty["duration_hours"],
            starts=duty["starts"],normal_mesh_force_n=duty["normal_force_magnitude_n"],loaded_flank=flank,
            peak_hertz_pressure_mpa=None if worst is None else worst["peak_pressure_mpa"],design_pressure_mpa=pressures,
            worst_contact=worst,profile=profile,members=member_rows,checks=checks))
    assessments=[]
    for role,material in materials.items():
        checks=[];flanks=[]
        declared=material.data_status=="declared" and all(s.strip() for s in (material.source_reference,material.applicable_conditions,material.redistribution_basis))
        checks.append(dict(name="Material and surface evidence",state="within_limit" if declared else "unassessed",
            note="Pressure-life data must apply to actual surface, lubricant, slide/roll, temperature and survival conditions. Declarations require independent review."))
        for flank in ("positive_torque","negative_torque"):
            selected=[next(m for m in r["members"] if m["role"]==role) for r in rows if r["loaded_flank"]==flank]
            damage=math.fsum(r["modeled_flank_damage"] for r in selected) if selected and all(r["modeled_flank_damage"] is not None for r in selected) else None
            cycles=math.fsum(r["tooth_contact_cycles"] for r in selected)
            flanks.append(dict(flank=flank,tooth_contact_cycles=cycles,modeled_damage=damage,
                state="not_exercised" if not selected else "unassessed" if damage is None else "within_limit" if damage<=1 else "outside_limit"))
        checks.append(dict(name="Actual load distribution and durability coverage",state="unassessed",
            note="Envelope/equal-pair sharing is not a verified stiffness or edge-contact solution. Transients, micropitting, wear, scuffing and physical qualification remain."))
        all_checks=checks+[c for row in rows for c in row["checks"] if not c["name"].startswith(("wheel:" if role=="pinion" else "pinion:"))]
        failed=any(c["state"]=="outside_limit" for c in all_checks+flanks)
        state="outside_entered_limits" if failed else "incomplete"
        if material.data_status=="synthetic":state="synthetic_outside_entered_limits" if failed else "synthetic_example"
        assessments.append(dict(role=role,assessment=state,flanks=flanks,checks=checks))
    inputs=asdict(study);digest=hashlib.sha256(json.dumps(inputs,sort_keys=True,separators=(",",":"),allow_nan=False).encode()).hexdigest()
    return dict(schema_version=1,app_version=__version__,method=METHOD,study_sha256=digest,
        source_study_sha256=source["study_sha256"],inputs=inputs,geometry=g,geometry_findings=findings,
        contact_path=None if path is None else {k:v for k,v in path.items() if k!="nodes"},cases=rows,members=assessments,
        production_approved=False,rated_output_torque_nm=None,rated_gearbox_life_hours=None,limitations=[
            "External spur involute contact with isotropic linear-elastic bodies, smooth surfaces, no friction traction and nominal alignment. Helical/internal/bevel/worm/cycloidal contacts are unsupported.",
            "Full-load envelope assigns all factored mesh force to each examined pair separately; it is not a simultaneous force distribution. Equal-pair sharing divides load by the ideal geometric count, not tooth stiffness.",
            "Continuous peak pressure uses exact interval endpoint limits, including load-sharing jumps. Interior curvature balance and pitch are included; plotted samples do not determine maxima.",
            "Pressure-life curves are user declarations and interpolate in log-log coordinates only. Surface condition, lubricant, sliding, reliability and material evidence are not supplied by a material name.",
            "A tooth flank is loaded once per gear revolution in this single-mesh model. Pinion/wheel counts differ by ratio; opposite torque flanks accumulate separately. Mesh frequency and spatial samples are not extra fatigue cycles.",
            "Damage uses the worst pressure station on each flank across the entered duty. The fixed geometry/sharing shape gives a common worst station across scalar factored cases. No transient/rainflow, load-sequence, wear or scuffing life is modeled.",
            "Sliding and surface speeds are ideal kinematics, not lubricant film, frictional heating or thermal capacity predictions.",
            "No verified production tooth strength, gearbox load rating or assembly durability is established."])


def contact_report_html(result):
    esc=lambda v:html.escape(str(v))
    fmt=lambda v:"Unassessed" if v is None else f"{v:.8g}"
    rows=[]
    for c in result["cases"]:
        position=None if c["worst_contact"] is None else c["worst_contact"]["relative_to_pitch_mm"]
        rows.append(f"<tr><td>{esc(c['name'])}</td><td>{esc(c['loaded_flank'].replace('_',' '))}</td><td>{fmt(c['normal_mesh_force_n'])}</td><td>{fmt(c['peak_hertz_pressure_mpa'])}</td><td>{fmt(c['design_pressure_mpa'])}</td><td>{fmt(position)}</td></tr>")
    members=[]
    for m in result["members"]:
        flanks="".join(f"<tr><td>{esc(f['flank'].replace('_',' '))}</td><td>{fmt(f['tooth_contact_cycles'])}</td><td>{fmt(f['modeled_damage'])}</td><td>{esc(f['state'].replace('_',' '))}</td></tr>" for f in m["flanks"])
        members.append(f"<h2>{m['role'].title()}: {esc(m['assessment'].replace('_',' '))}</h2><table><tr><th>Flank</th><th>Cycles per tooth</th><th>Modeled damage</th><th>State</th></tr>{flanks}</table>")
    findings="".join(f"<li>{esc(f)}</li>" for f in result["geometry_findings"])
    checks=""
    for c in result["cases"]:
        details="".join(f"<tr><td>{m['role'].title()}</td><td>{fmt(m['tooth_contact_cycles'])}</td><td>{fmt(m['cycles_to_failure'])}</td><td>{fmt(m['modeled_flank_damage'])}</td><td>{esc(m['curve_state'].replace('_',' '))}</td></tr>" for m in c['members'])
        checks+=f"<h3>{esc(c['name'])}</h3><table><tr><th>Member</th><th>Cycles per tooth</th><th>Curve failure cycles</th><th>Modeled damage</th><th>Range</th></tr>{details}</table><ul>"+"".join(f"<li><strong>{esc(k['name'])}: {esc(k['state'].replace('_',' '))}.</strong> {esc(k['note'])}</li>" for k in c["checks"])+"</ul>"
    provenance="".join(f"<li><strong>{m['role'].title()} {esc(c['name'])}: {esc(c['state'].replace('_',' '))}.</strong> {esc(c['note'])}</li>" for m in result["members"] for c in m["checks"])
    limits="".join(f"<li>{esc(l)}</li>" for l in result["limitations"])
    return ("<!doctype html><html><head><meta charset='utf-8'><title>Tooth contact study</title><style>body{font-family:Arial,sans-serif;margin:24px;max-width:1250px}table{border-collapse:collapse}td,th{border:1px solid #888;padding:6px}pre{white-space:pre-wrap}</style></head><body>"
        f"<h1>{esc(result['inputs']['name'])}</h1><p><strong>Elastic tooth-contact study — no production gearbox rating</strong></p><p>GearForge {esc(result['app_version'])}; method {esc(result['method'])}. Sharing: {esc(result['inputs']['load_sharing'].replace('_',' '))}.</p>"
        f"<ul>{findings}</ul><table><tr><th>Case</th><th>Loaded flank</th><th>Mesh normal N</th><th>Peak Hertz MPa</th><th>Design MPa</th><th>From pitch mm</th></tr>{''.join(rows)}</table>"
        +"".join(members)+f"<h2>Evidence and checks</h2><ul>{provenance}</ul>{checks}<h2>Method limits</h2><ul>{limits}</ul><h2>Complete inputs</h2><pre>{esc(json.dumps(result['inputs'],indent=2,allow_nan=False))}</pre><p>Input fingerprint: {esc(result['study_sha256'])}</p></body></html>")


def export_contact_study(study,destination):
    from .maintenance import write_manifest
    result=calculate_contact_study(study);dest=Path(destination).absolute()
    if dest.exists() or dest.is_symlink():raise FileExistsError("Choose a new contact assessment directory")
    dest.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".gearforge-contact-",dir=dest.parent) as temporary:
        stage=Path(temporary)/"study";stage.mkdir();study.save(stage/"design.gearforge-contact")
        atomic_text(stage/"calculation.json",json.dumps(result,indent=2,allow_nan=False))
        atomic_text(stage/"report.html",contact_report_html(result))
        manifest=write_manifest(stage,kind="gearforge-contact-study",method=METHOD,study_sha256=result["study_sha256"],production_approved=False)
        if dest.exists() or dest.is_symlink():raise FileExistsError("Contact output directory already exists")
        stage.rename(dest)
    return dict(destination=str(dest),files=len(manifest["files"])+1,study_sha256=result["study_sha256"],production_approved=False)
