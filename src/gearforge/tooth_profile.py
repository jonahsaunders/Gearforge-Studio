"""Original rolling-rack envelope for external spur manufacturing studies.

The analytic cutter envelope is distinct from the sampled prototype CAD. No
material properties, rating factors, standards tables or third-party code are
used here. Coordinates are millimetres; the central tooth points along +Y.
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
from .engineering import EngineeringStudy, _integer, _model, _text, calculate_study, involute
from .models import atomic_text, finite, read_text_limited, strict_json

METHOD = 'rolling-rack-spur-1'
MAX_BYTES = 2_000_000


@dataclass
class ToothProfileStudy:
    name: str = 'Rack-generated tooth profile'
    source: EngineeringStudy = field(default_factory=EngineeringStudy)
    role: str = 'pinion'
    cutter_depth_coefficient: float = 1.25
    cutter_tip_radius_coefficient: float | None = None
    tooth_thickness_reduction_mm: float = 0.0
    sampling_tolerance_mm: float = 0.005
    data_status: str = 'unverified'
    cutter_reference: str = ''
    redistribution_basis: str = ''
    notes: str = ''
    schema_version: int = 1

    def validate(self):
        _integer(self.schema_version, 'Profile schema', 1, 1)
        if not isinstance(self.source, EngineeringStudy):raise ValueError('A retained engineering study is required')
        self.source.validate()
        if self.role not in ('pinion', 'wheel'):raise ValueError('Choose pinion or wheel')
        if self.data_status not in ('unverified', 'synthetic', 'declared'):raise ValueError('Invalid cutter data status')
        for name in ('name', 'cutter_reference', 'redistribution_basis', 'notes'):
            _text(getattr(self, name), name, 10000 if name == 'notes' else 2000, name == 'name')
        for name, low, high in (('cutter_depth_coefficient', .5, 2),
                                ('tooth_thickness_reduction_mm', 0, 50),
                                ('sampling_tolerance_mm', .0001, .1)):
            setattr(self, name, finite(getattr(self, name), name, low, high))
        if self.cutter_tip_radius_coefficient is not None:
            self.cutter_tip_radius_coefficient = finite(self.cutter_tip_radius_coefficient, 'Cutter tip radius coefficient', .001, 1)

    def save(self, path):
        self.validate();data = json.dumps(asdict(self), indent=2, allow_nan=False)
        if len(data.encode('utf-8')) > MAX_BYTES:raise ValueError('Tooth profile exceeds 2 MB')
        atomic_text(Path(path), data)

    @classmethod
    def from_dict(cls, data):
        if not isinstance(data, dict) or 'source' not in data:raise ValueError('Incomplete tooth profile study')
        data = dict(data);data['source'] = EngineeringStudy.from_dict(data['source'])
        result = _model(cls, data);result.validate();return result

    @classmethod
    def load(cls, path):
        return cls.from_dict(strict_json(read_text_limited(Path(path), MAX_BYTES, 'Tooth profile study')))


def profile_from_study(source, role='pinion'):
    result = ToothProfileStudy(source=EngineeringStudy.from_dict(asdict(source)), role=role)
    result.validate();return result


def synthetic_profile_example():
    result = ToothProfileStudy(cutter_tip_radius_coefficient=.38, data_status='synthetic',
        cutter_reference='Original numerical fixture: rounded symmetric rack, not a selected cutting tool.',
        redistribution_basis='Original GearForge fixture under Apache-2.0.',
        notes='Geometry verification example only. Actual cutter, finishing, tolerances and inspection remain to be selected.')
    result.validate();return result


class RackProfile:
    """Analytic half-tooth with proven monotone polar angle in its supported domain."""
    def __init__(self, study):
        study.validate();pair = study.source.pair
        if pair.pinion_helix_angle_deg != 0:raise ValueError('A helical hob envelope is not a spur rack section; only external spur profiles are implemented')
        if study.cutter_tip_radius_coefficient is None:raise ValueError('Actual cutter tip radius is unknown')
        from .engineering import pair_geometry
        geometry = pair_geometry(pair);member = geometry[study.role]
        self.m = pair.normal_module_mm
        self.z = pair.pinion_teeth if study.role == 'pinion' else pair.wheel_teeth
        self.alpha = math.radians(pair.normal_pressure_angle_deg)
        self.shift = self.m * (pair.pinion_profile_shift if study.role == 'pinion' else pair.wheel_profile_shift)
        self.R = self.m * self.z / 2;self.rb = self.R * math.cos(self.alpha)
        self.ra = member['tip_diameter_mm'] / 2
        self.h = self.m * study.cutter_depth_coefficient
        self.rho = self.m * study.cutter_tip_radius_coefficient
        self.s0 = math.pi * self.m / 4 - study.tooth_thickness_reduction_mm / 2
        self.vc = -self.h + self.rho
        self.uc = self.s0 + (self.h-self.rho)*math.tan(self.alpha) + self.rho/math.cos(self.alpha)
        self.D = self.h - self.rho - self.shift
        self.rf = self.R + self.shift - self.h
        s = math.sin(self.alpha)
        if self.s0 <= 0 or self.uc >= math.pi*self.m/2:
            raise ValueError('Cutter corners overlap or reference tooth thickness is exhausted')
        if self.rf <= 0 or self.ra <= max(self.rf, self.rb):raise ValueError('Invalid root or tip radius')
        # Envelope speed K = [R*rho*s^3 + rho*D*s + D^2]/(R*s^3).
        # Polar derivative has the additional factor H = R*s^2-rho*s-D.
        # Their minima on sin(alpha)..1 prove regularity and no angular fold.
        q_sites = [s, 1.]
        if self.D < 0:
            critical = math.sqrt(-self.D/(3*self.R))
            if s < critical < 1:q_sites.append(critical)
        h_sites = [s, 1.]
        critical = self.rho/(2*self.R)
        if s < critical < 1:h_sites.append(critical)
        self.minimum_speed_numerator = min(self.R*self.rho*t**3+self.rho*self.D*t+self.D**2 for t in q_sites)
        self.minimum_polar_factor = min(self.R*t*t-self.rho*t-self.D for t in h_sites)
        if self.minimum_speed_numerator <= 1e-12*self.m**2 or self.minimum_polar_factor <= 1e-10*self.m:
            raise ValueError('Cutter produces undercut, a cusp or a folded root envelope; trimmed undercut geometry is not yet implemented')
        self.join = self.fillet(self.alpha)
        self.rj = math.hypot(*self.join);self.phij = math.atan2(self.join[0], self.join[1])
        self.phif = self.uc/self.R
        self.half_pitch = (self.s0+self.shift*math.tan(self.alpha))/self.R
        self.phia = self.flank_angle(self.ra)
        if not 0 < self.phia < self.phij < self.phif < math.pi/self.z or self.rj >= self.ra:
            raise ValueError('Pointed/crossed tips, overlapping roots, or cutter fillet reaching the tip prevents a supported profile')
        if math.dist(self.join, self.flank(self.rj)) > 1e-8*self.m:
            raise ValueError('Cutter envelope did not join the active involute')

    def cutter(self, psi):return (self.uc-self.rho*math.cos(psi), self.vc-self.rho*math.sin(psi))

    def fillet(self, psi):
        u, v = self.cutter(psi);w = self.shift+v
        horizontal = w/math.tan(psi);theta = (horizontal-u)/self.R
        vertical = self.R+w;c, s = math.cos(theta), math.sin(theta)
        return (horizontal*c-vertical*s, horizontal*s+vertical*c)

    def flank_angle(self, radius):
        return self.half_pitch + involute(self.alpha) - involute(math.acos(self.rb/radius))

    def flank(self, radius):
        angle = self.flank_angle(radius);return (radius*math.sin(angle), radius*math.cos(angle))

    def radius_at_angle(self, phi):
        """Material boundary on a ray; angle clockwise from central +Y tooth."""
        phi = abs(float(phi))
        if not math.isfinite(phi) or phi > math.pi/self.z+1e-12:raise ValueError('Ray is outside this tooth sector')
        if phi <= self.phia:return self.ra
        if phi >= self.phif:return self.rf
        if phi <= self.phij:
            low, high = self.rj, self.ra
            for _ in range(65):
                mid = (low+high)/2
                if self.flank_angle(mid) > phi:low = mid
                else:high = mid
            return (low+high)/2
        low, high = self.alpha, math.pi/2
        for _ in range(65):
            mid = (low+high)/2;x,y = self.fillet(mid)
            if math.atan2(x,y) < phi:low = mid
            else:high = mid
        return math.hypot(*self.fillet((low+high)/2))

    def segments(self, tolerance):
        return [
            ('tip', adaptive_points(lambda a:(self.ra*math.sin(a), self.ra*math.cos(a)), 0, self.phia, tolerance)),
            ('involute', adaptive_points(self.flank, self.ra, self.rj, tolerance)),
            ('generated root', adaptive_points(self.fillet, self.alpha, math.pi/2, tolerance)),
            ('root land', adaptive_points(lambda a:(self.rf*math.sin(a), self.rf*math.cos(a)), self.phif, math.pi/self.z, tolerance)),
        ]

    def outline(self, segments):
        half = [p for _,points in segments for p in points[:-1]] + [segments[-1][1][-1]]
        sector = [(-x,y) for x,y in reversed(half)] + half[1:]
        if (len(sector)-1)*self.z>200000:raise ValueError('Profile exceeds 200,000 vertices; relax sampling tolerance')
        points = []
        for tooth in range(self.z):
            angle = -2*math.pi*tooth/self.z;c,s = math.cos(angle), math.sin(angle)
            points.extend((x*c-y*s,x*s+y*c) for x,y in sector[:-1])
        return points


def chord_distance(point, first, last):
    dx,dy = last[0]-first[0],last[1]-first[1];length = dx*dx+dy*dy
    t = max(0.,min(1.,((point[0]-first[0])*dx+(point[1]-first[1])*dy)/length)) if length else 0.
    return math.hypot(point[0]-first[0]-t*dx,point[1]-first[1]-t*dy)


def adaptive_points(function, start, end, tolerance):
    """Refine against three interior probes; requested tolerance is not a certified bound."""
    output = [function(start)]
    def split(a,b,first,last,depth):
        sites = [a+(b-a)*fraction for fraction in (.25,.5,.75)]
        probes = [function(t) for t in sites]
        if max(chord_distance(p,first,last) for p in probes) > tolerance/2:
            if depth>=22:raise ValueError('Profile sampling did not converge')
            split(a,sites[1],first,probes[1],depth+1);split(sites[1],b,probes[1],last,depth+1)
        else:output.append(last)
    split(start,end,output[0],function(end),0)
    return output


def calculate_profile_study(study):
    study.validate();source = calculate_study(study.source);inputs = asdict(study)
    digest = hashlib.sha256(json.dumps(inputs,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
    result = dict(schema_version=1,app_version=__version__,method=METHOD,inputs=inputs,study_sha256=digest,
        source_study_sha256=source['study_sha256'],profile_available=False,geometry=None,segments=[],outline_mm=[],findings=[],
        production_approved=False,rated_output_torque_nm=None,rated_gearbox_life_hours=None,
        limitations=[
            'External symmetric spur gears generated by a straight rack with a circular cutter tip only. No helical hob, protuberance, asymmetric cutter, grinding stock, edge break or finishing simulation.',
            'Undercut, cusps and angular folds are rejected analytically. This method does not trim or export those envelopes.',
            'Source pair tip shortening is retained. Cutter depth explicitly sets the root and may differ from the source study\'s conventional root diameter.',
            'Tooth thickness reduction is an individual member reduction at its reference circle, not assembled backlash. Pair tolerances, deflection and thermal growth remain unassessed.',
            'Analytic geometry is separate from display/export polylines. Adaptive sampling uses interior probes and a safety factor, not a certified maximum chord-error bound.',
            'The active-contact check compares the source ideal line of action with this member\'s involute start only; it does not verify mating cutter geometry, loaded contact or assembly clearances.',
            'Cutter provenance and geometry do not establish root stress, material fatigue, manufacturing accuracy or production load ratings. Prototype CAD remains a separate sampled approximation.'])
    if study.data_status!='declared':result['findings'].append('Cutter inputs are '+study.data_status+'; actual manufacturing evidence is not established.')
    result['findings'].extend('Source geometry: '+issue for issue in source['geometry']['issues'])
    if not study.cutter_reference.strip() or not study.redistribution_basis.strip():result['findings'].append('Cutter source and redistribution basis must be established for shared manufacturing evidence.')
    try:profile = RackProfile(study)
    except ValueError as exc:result['findings'].append(str(exc));return result
    segments = profile.segments(study.sampling_tolerance_mm)
    outline = profile.outline(segments)
    geometry = source['geometry'];other = geometry['wheel' if study.role=='pinion' else 'pinion']
    tangent = geometry['operating_center_distance_mm']*math.sin(math.radians(geometry['operating_pressure_angle_deg']))
    start_roll = tangent - math.sqrt((other['tip_diameter_mm']/2)**2-(other['base_diameter_mm']/2)**2)
    active_start = math.hypot(profile.rb,start_roll) if start_roll>=0 else None
    active_clear = active_start is not None and active_start >= profile.rj-1e-9*profile.m
    root_delta = 2*profile.rf-geometry[study.role]['root_diameter_mm']
    if abs(root_delta)>1e-9*profile.m:result['findings'].append('Declared cutter depth changes the root diameter from the source study.')
    if not active_clear:result['findings'].append('The mating tip reaches below the generated involute start; nominal full-path involute engagement is not supported.')
    result.update(profile_available=True,geometry=dict(teeth=profile.z,module_mm=profile.m,
        reference_radius_mm=profile.R,base_radius_mm=profile.rb,tip_radius_mm=profile.ra,
        generated_root_radius_mm=profile.rf,involute_start_radius_mm=profile.rj,
        nominal_active_start_radius_mm=active_start,nominal_active_path_above_fillet=active_clear,
        reference_tooth_thickness_mm=2*profile.R*profile.half_pitch,
        tip_tooth_thickness_mm=2*profile.ra*profile.phia,cutter_depth_mm=profile.h,
        cutter_tip_radius_mm=profile.rho,cutter_tip_flat_width_mm=math.pi*profile.m-2*profile.uc,
        root_diameter_difference_from_source_mm=root_delta,vertex_count=len(outline),
        sampling_tolerance_mm=study.sampling_tolerance_mm,
        analytic_minimum_speed_numerator_mm2=profile.minimum_speed_numerator,
        analytic_minimum_polar_factor_mm=profile.minimum_polar_factor),
        segments=[dict(name=name,points_mm=points) for name,points in segments],outline_mm=outline)
    return result


def profile_svg(result):
    if not result['profile_available']:raise ValueError('No supported tooth profile to draw')
    r = result['geometry']['tip_radius_mm'];margin = r*.08
    points = ' '.join(f'{x:.12g},{-y:.12g}' for x,y in result['outline_mm'])
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{-r-margin} {-r-margin} {2*(r+margin)} {2*(r+margin)}">'
        '<title>Rack-generated spur outline — millimetres, sampled geometry, no production rating</title>'
        f'<polygon points="{points}" fill="#e0f4ef" stroke="#166a5e" stroke-width="{r/500}"/></svg>')


def profile_dxf(result):
    if not result['profile_available']:raise ValueError('No supported tooth profile to export')
    # ASCII DXF R2000: a single closed lightweight polyline, explicit millimetres.
    lines=['0','SECTION','2','HEADER','9','$ACADVER','1','AC1015','9','$INSUNITS','70','4',
           '0','ENDSEC','0','SECTION','2','ENTITIES','0','LWPOLYLINE','100','AcDbEntity','8','SAMPLED_RACK_PROFILE',
           '100','AcDbPolyline','90',str(len(result['outline_mm'])),'70','1']
    for x,y in result['outline_mm']:lines.extend(['10',format(x,'.16g'),'20',format(y,'.16g')])
    return '\n'.join(lines+['0','ENDSEC','0','EOF'])+'\n'


def profile_report_html(result):
    esc=lambda value:html.escape(str(value))
    rows=''.join(f'<tr><td>{esc(k.replace("_"," "))}</td><td>{esc(v)}</td></tr>' for k,v in (result['geometry'] or {}).items())
    findings=''.join(f'<li>{esc(v)}</li>' for v in result['findings'])
    limits=''.join(f'<li>{esc(v)}</li>' for v in result['limitations'])
    return ('<!doctype html><html><head><meta charset="utf-8"><title>Generated tooth profile</title>'
        '<style>body{font-family:Arial,sans-serif;max-width:1100px;margin:24px}td{padding:5px;border:1px solid #aaa}table{border-collapse:collapse}pre{white-space:pre-wrap}</style></head><body>'
        f'<h1>{esc(result["inputs"]["name"])}</h1><p><strong>Manufacturing geometry study — no production rating</strong></p>'
        f'<p>GearForge {esc(result["app_version"])}; method {esc(result["method"])}; {esc(result["inputs"]["role"])}.</p>'
        f'<p>Supported profile available: {result["profile_available"]}</p><ul>{findings}</ul><table>{rows}</table>'
        f'<h2>Scope and remaining work</h2><ul>{limits}</ul><h2>Complete inputs</h2><pre>{esc(json.dumps(result["inputs"],indent=2))}</pre>'
        f'<p>Input fingerprint: {result["study_sha256"]}</p></body></html>')


def export_profile_study(study,destination):
    from .maintenance import write_manifest
    result=calculate_profile_study(study);dest=Path(destination).absolute()
    if dest.exists() or dest.is_symlink():raise FileExistsError('Choose a new tooth-profile directory')
    dest.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.gearforge-profile-',dir=dest.parent) as temporary:
        stage=Path(temporary)/'study';stage.mkdir();study.save(stage/'design.gearforge-tooth')
        atomic_text(stage/'calculation.json',json.dumps(result,indent=2,allow_nan=False))
        atomic_text(stage/'report.html',profile_report_html(result))
        if result['profile_available']:
            atomic_text(stage/'profile.svg',profile_svg(result));atomic_text(stage/'profile.dxf',profile_dxf(result))
            atomic_text(stage/'profile.csv','x_mm,y_mm\n'+''.join(f'{x:.16g},{y:.16g}\n' for x,y in result['outline_mm']))
        manifest=write_manifest(stage,kind='gearforge-tooth-profile',method=METHOD,study_sha256=result['study_sha256'],production_approved=False)
        if dest.exists() or dest.is_symlink():raise FileExistsError('Tooth-profile directory already exists')
        stage.rename(dest)
    return dict(destination=str(dest),files=len(manifest['files'])+1,study_sha256=result['study_sha256'],
        profile_available=result['profile_available'],production_approved=False)
