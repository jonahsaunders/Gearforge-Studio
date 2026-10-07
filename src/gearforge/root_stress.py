"""Explicit two-dimensional elastic stress studies on generated spur roots.

This is a controlled numerical model, not an ISO/AGMA rating or a life model.
Cut surfaces, support radius, width, loading patch and material are retained
inputs. Three mesh levels and a wider-sector check expose model sensitivity.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
import hashlib
import html
import csv
import io
import json
import math
from pathlib import Path
import tempfile

import numpy as np

from . import __version__
from .bearings import optional_number
from .elasticity import PlaneElasticSystem, MAX_ELEMENTS, shape, stress_measures
from .engineering import _integer, _model, _text, pair_geometry
from .models import atomic_text, finite, read_text_limited, strict_json
from .tooth_profile import ToothProfileStudy, RackProfile, calculate_profile_study, synthetic_profile_example

METHOD='generated-spur-q9-elastic-1'
MAX_BYTES=3_000_000


@dataclass
class RootLoadCase:
    case_name: str = 'Continuous rated-input target'
    normal_load_multiplier: float | None = None
    load_share: float | None = None
    temperature_c: float | None = None
    factor_basis: str = ''

    def validate(self):
        _text(self.case_name,'Root load case',120,required=True);_text(self.factor_basis,'Load factor basis',4000)
        for name,lo,hi in [('normal_load_multiplier',1,100),('load_share',0,1),('temperature_c',-80,200)]:
            setattr(self,name,optional_number(getattr(self,name),name,lo,hi))


@dataclass
class RootStressStudy:
    name: str = 'Generated tooth-root elastic study'
    source: ToothProfileStudy = field(default_factory=ToothProfileStudy)
    youngs_modulus_mpa: float | None = None
    poisson_ratio: float | None = None
    effective_face_width_mm: float | None = None
    maximum_elastic_stress_mpa: float | None = None
    minimum_temperature_c: float | None = None
    maximum_temperature_c: float | None = None
    material_status: str = 'unverified'
    material_reference: str = ''
    redistribution_basis: str = ''
    plane_mode: str = 'plane_stress'
    support_radius_mm: float | None = None
    sector_teeth: int = 5
    support_basis: str = ''
    patch_half_width_mm: float | None = None
    load_positions: list[float] = field(default_factory=lambda:[.2,.5,.8])
    angular_divisions_per_tooth: int = 16
    radial_layers: int = 8
    convergence_tolerance_percent: float = 5.0
    cases: list[RootLoadCase] = field(default_factory=lambda:[RootLoadCase()])
    notes: str = ''
    schema_version: int = 1

    def validate(self):
        _integer(self.schema_version,'Root study schema',1,1)
        if not isinstance(self.source,ToothProfileStudy):raise ValueError('Retained cutter/profile study is required')
        self.source.validate()
        if self.material_status not in ('unverified','synthetic','declared'):raise ValueError('Invalid material evidence status')
        if self.plane_mode not in ('plane_stress','plane_strain'):raise ValueError('Choose plane stress or plane strain')
        for name in ('name','material_reference','redistribution_basis','support_basis','notes'):
            _text(getattr(self,name),name,10000 if name=='notes' else 4000,name=='name')
        for name,lo,hi in [('youngs_modulus_mpa',1,1e6),('poisson_ratio',0,.45 if self.plane_mode=='plane_strain' else .49),
            ('effective_face_width_mm',.001,self.source.source.pair.face_width_mm),('maximum_elastic_stress_mpa',.001,100000),
            ('minimum_temperature_c',-80,200),('maximum_temperature_c',-80,200),('support_radius_mm',.001,50000),('patch_half_width_mm',.0001,50)]:
            setattr(self,name,optional_number(getattr(self,name),name,lo,hi))
        if self.minimum_temperature_c is not None and self.maximum_temperature_c is not None and self.minimum_temperature_c>self.maximum_temperature_c:
            raise ValueError('Material temperature range is reversed')
        _integer(self.sector_teeth,'Sector teeth',3,9)
        if self.sector_teeth%2!=1:raise ValueError('Use an odd number of teeth centered on the loaded tooth')
        _integer(self.angular_divisions_per_tooth,'Base angular divisions per tooth',8,64)
        _integer(self.radial_layers,'Base radial layers',4,24)
        self.convergence_tolerance_percent=finite(self.convergence_tolerance_percent,'Convergence tolerance percent',.1,20)
        if not isinstance(self.load_positions,list) or not 1<=len(self.load_positions)<=12:raise ValueError('Enter 1..12 ordered load positions')
        self.load_positions=[finite(p,'Active-path fraction',0,1) for p in self.load_positions]
        if any(a>=b for a,b in zip(self.load_positions,self.load_positions[1:])):raise ValueError('Load positions must strictly increase')
        if not isinstance(self.cases,list) or len(self.cases)!=len(self.source.source.duty):raise ValueError('Define every source duty case')
        for case in self.cases:
            if not isinstance(case,RootLoadCase):raise ValueError('Invalid root load case')
            case.validate()
        if {c.case_name for c in self.cases}!={d.name for d in self.source.source.duty}:raise ValueError('Root cases must match source duty names')

    @classmethod
    def from_dict(cls,data):
        if not isinstance(data,dict) or not isinstance(data.get('cases'),list) or len(data['cases'])>200:raise ValueError('Invalid root study')
        data=dict(data);data['source']=ToothProfileStudy.from_dict(data.get('source'))
        data['cases']=[_model(RootLoadCase,c) for c in data['cases']]
        result=_model(cls,data);result.validate();return result

    @classmethod
    def load(cls,path):return cls.from_dict(strict_json(read_text_limited(Path(path),MAX_BYTES,'Root stress study')))

    def save(self,path):
        self.validate();text=json.dumps(asdict(self),indent=2,allow_nan=False)
        if len(text.encode('utf-8'))>MAX_BYTES:raise ValueError('Root study exceeds 3 MB')
        atomic_text(Path(path),text)


def root_from_profile(source):
    source=ToothProfileStudy.from_dict(asdict(source))
    result=RootStressStudy(source=source,cases=[RootLoadCase(case_name=c.name) for c in source.source.duty])
    result.validate();return result


def synthetic_root_example():
    study=root_from_profile(synthetic_profile_example())
    study.youngs_modulus_mpa=210000.;study.poisson_ratio=.3;study.effective_face_width_mm=20.
    study.maximum_elastic_stress_mpa=200.;study.minimum_temperature_c=20.;study.maximum_temperature_c=80.
    study.material_status='synthetic';study.material_reference='Invented isotropic elastic fixture, not supplier/material qualification.'
    study.redistribution_basis='Original GearForge numerical fixture, Apache-2.0.'
    study.support_radius_mm=10.;study.patch_half_width_mm=.15
    study.sector_teeth=7
    study.support_basis='Invented plane-stress sector clamped on the 10 mm inner arc; cut sides traction-free. Numerical verification only.'
    for case in study.cases:
        case.normal_load_multiplier=1.;case.load_share=1.;case.temperature_c=40.
        case.factor_basis='Synthetic full-mesh torque, uniform face width, smooth pressure patch; no measured dynamic or alignment factor.'
    study.validate();return study


def load_patches(study,profile):
    geometry=pair_geometry(study.source.source.pair)
    other=geometry['wheel' if study.source.role=='pinion' else 'pinion']
    length=geometry['operating_center_distance_mm']*math.sin(math.radians(geometry['operating_pressure_angle_deg']))
    lower=length-math.sqrt((other['tip_diameter_mm']/2)**2-(other['base_diameter_mm']/2)**2)
    upper=math.sqrt(profile.ra**2-profile.rb**2)
    if lower<0 or lower>=upper:raise ValueError('No supported nominal active contact interval')
    patches=[]
    for fraction in study.load_positions:
        roll=lower+(upper-lower)*fraction;radius=math.hypot(profile.rb,roll)
        arc=(radius**2-profile.rb**2)/(2*profile.rb)
        lo=arc-study.patch_half_width_mm;hi=arc+study.patch_half_width_mm
        if lo<=0:raise ValueError('Load patch reaches below the base-circle involute')
        rlo=math.sqrt(profile.rb**2+2*profile.rb*lo);rhi=math.sqrt(profile.rb**2+2*profile.rb*hi)
        if rlo<=profile.rj or rhi>=profile.ra:
            raise ValueError(f'Load patch at path fraction {fraction:g} crosses the involute start or tooth tip; change position or patch width')
        patches.append(dict(fraction=fraction,arc_center_mm=arc,radius_mm=radius,
            minimum_angle_rad=profile.flank_angle(rhi),maximum_angle_rad=profile.flank_angle(rlo)))
    return patches


def root_mesh(study,profile,patches,refinement=1,sector_teeth=None):
    teeth=study.sector_teeth if sector_teeth is None else sector_teeth
    if teeth>=profile.z:raise ValueError('The truncated sector must contain fewer teeth than the full gear')
    inner=study.support_radius_mm
    if inner is None or inner>=profile.rf-.1*profile.m:raise ValueError('Support radius must leave at least 0.1 module of material below the generated root')
    nrad=study.radial_layers*refinement;pitch=2*math.pi/profile.z
    anchors=[-teeth*pitch/2,teeth*pitch/2]
    for k in range(-(teeth//2),teeth//2+1):
        for local in (-profile.phif,-profile.phij,-profile.phia,0,profile.phia,profile.phij,profile.phif):anchors.append(k*pitch+local)
    for patch in patches:
        for angle in (patch['minimum_angle_rad'],patch['maximum_angle_rad']):anchors.extend([angle,-angle])
    # Subdivide between required geometry/load breakpoints. Inserting them into
    # an unrelated uniform grid could create arbitrarily thin sliver columns.
    anchors=np.unique(np.round(anchors,14));angles=[];step=pitch/(study.angular_divisions_per_tooth*refinement)
    for a,b in zip(anchors,anchors[1:]):angles.extend(np.linspace(a,b,max(1,math.ceil((b-a)/step))+1)[:-1])
    angles=np.array([*angles,anchors[-1]]);nang=len(angles)
    if (nang-1)*nrad>MAX_ELEMENTS:raise ValueError('Elastic mesh exceeds 40,000 cells; reduce base divisions or domain size')
    local=(angles+pitch/2)%pitch-pitch/2
    outer=np.array([profile.radius_at_angle(a) for a in local])
    radial=1-(1-np.linspace(0,1,nrad+1))**1.5
    radii=inner+radial[:,None]*(outer[None,:]-inner)
    nodes=np.stack((radii*np.sin(angles),radii*np.cos(angles)),axis=-1).reshape(-1,2)
    first=(np.arange(nrad)[:,None]*nang+np.arange(nang-1)[None,:]).ravel()
    elements=np.column_stack((first,first+1,first+nang+1,first+nang))
    outer_nodes=np.arange(nrad*nang,(nrad+1)*nang)
    mids=(angles[:-1]+angles[1:])/2
    tooth_indices=np.floor((mids+pitch/2)/pitch).astype(int)
    local_mids=mids-tooth_indices*pitch
    root_columns=np.flatnonzero((abs(local_mids)>profile.phij-1e-12)&(abs(local_mids)<profile.phif+1e-12))
    root_elements=(nrad-1)*(nang-1)+root_columns
    # Quadratic displacement nodes share edge midpoints. Geometry remains the
    # explicit polygonal mesh and therefore has the Q4 Jacobian positivity proof.
    coordinates=nodes.tolist();midpoints={};quadratic=[]
    for element in elements:
        middle=[]
        for a,b in zip(element,np.roll(element,-1)):
            edge=tuple(sorted((int(a),int(b))))
            if edge not in midpoints:
                midpoints[edge]=len(coordinates);coordinates.append(((nodes[a]+nodes[b])/2).tolist())
            middle.append(midpoints[edge])
        center=len(coordinates);coordinates.append(nodes[element].mean(axis=0).tolist())
        quadratic.append([*element,*middle,center])
    fixed_nodes=[*range(nang),*(midpoints[(i,i+1)] for i in range(nang-1))]
    outer_midpoints=[midpoints[(int(a),int(b))] for a,b in zip(outer_nodes,outer_nodes[1:])]
    return dict(nodes=np.array(coordinates),elements=np.array(quadratic),angles=angles,outer_nodes=outer_nodes,outer_midpoints=outer_midpoints,
        fixed_dofs=(2*np.array(fixed_nodes)[:,None]+[0,1]).ravel(),root_elements=root_elements,root_columns=root_columns,
        root_tooth_indices=tooth_indices[root_columns],sector_teeth=teeth,radial_layers=nrad)


def patch_forces(study,profile,mesh,patch,flank):
    """Consistent boundary tractions normalized to exactly +/-1 N mm torque."""
    if flank not in ('left','right'):raise ValueError('Choose left or right flank')
    force=np.zeros(2*len(mesh['nodes']));sign=1 if flank=='right' else -1
    abscissae,weights=np.polynomial.legendre.leggauss(4)
    for i,(a,b) in enumerate(zip(mesh['angles'],mesh['angles'][1:])):
        mid=sign*(a+b)/2
        if not patch['minimum_angle_rad']-1e-12<=mid<=patch['maximum_angle_rad']+1e-12:continue
        indices=np.array([mesh['outer_nodes'][i],mesh['outer_midpoints'][i],mesh['outer_nodes'][i+1]])
        points=mesh['nodes'][indices];length=math.dist(points[0],points[2])
        for xi,weight in zip(abscissae,weights):
            n=np.array([xi*(xi-1)/2,1-xi*xi,xi*(xi+1)/2]);point=n@points;radius=float(np.linalg.norm(point))
            arc=(radius*radius-profile.rb**2)/(2*profile.rb)
            magnitude=max(0.,1-((arc-patch['arc_center_mm'])/study.patch_half_width_mm)**2)
            phi=math.atan2(sign*point[0],point[1]);alpha=math.acos(min(1.,profile.rb/radius))
            normal=np.array([-sign*math.cos(phi-alpha),math.sin(phi-alpha)])
            for node,fraction in zip(indices,n):force[2*node:2*node+2]+=normal*magnitude*weight*length/2*fraction
    nodal=force.reshape(-1,2)
    moment=float(np.sum(mesh['nodes'][:,0]*nodal[:,1]-mesh['nodes'][:,1]*nodal[:,0]))
    if not math.isfinite(moment) or sign*moment<=1e-15:raise ValueError('Pressure patch could not resolve an inward torque-bearing load')
    return force/abs(moment)


def solve_root_mesh(study,profile,patches,refinement,sector_teeth=None,keep_fields=False):
    mesh=root_mesh(study,profile,patches,refinement,sector_teeth)
    if keep_fields and len(mesh['nodes'])*len(patches)*2>750000:raise ValueError('Mesh/load field output exceeds the bounded study size')
    system=PlaneElasticSystem(mesh['nodes'],mesh['elements'],study.youngs_modulus_mpa,study.poisson_ratio,
        study.effective_face_width_mm,study.plane_mode)
    requests=[(patch,flank) for patch in patches for flank in ('left','right')]
    forces=np.column_stack([patch_forces(study,profile,mesh,patch,flank) for patch,flank in requests])
    solved=system.solve(forces,mesh['fixed_dofs']);responses=[]
    for column,(patch,flank) in enumerate(requests):
        u=solved['displacements'][:,column];rows=[]
        for xi in (-1,-.5,0,.5,1):
            stress=system.stress_at(u,mesh['root_elements'],xi,1);vm,tension=stress_measures(stress)
            positions=np.einsum('n,eni->ei',shape(xi,1,9),system.coordinates[mesh['root_elements']])
            for i,point in enumerate(positions):
                rows.append(dict(x_mm=float(point[0]),y_mm=float(point[1]),tooth_index=int(mesh['root_tooth_indices'][i]),
                    stress_mpa_per_n_mm=stress[i].tolist(),von_mises_mpa_per_n_mm=float(vm[i]),tensile_mpa_per_n_mm=float(tension[i])))
        # Retain every element-side value at shared points; no stress averaging.
        peak_vm=max(rows,key=lambda r:r['von_mises_mpa_per_n_mm']);peak_tension=max(rows,key=lambda r:r['tensile_mpa_per_n_mm'])
        domain_vm=np.zeros(len(mesh['elements']))
        for xi,eta in system.gauss:
            vm,_=stress_measures(system.stress_at(u,xi=xi,eta=eta));domain_vm=np.maximum(domain_vm,vm)
        force=forces[:,column].reshape(-1,2)
        response=dict(position_fraction=patch['fraction'],flank=flank,unit_torque_n_mm=-1. if flank=='left' else 1.,
            root_von_mises_mpa_per_n_mm=peak_vm['von_mises_mpa_per_n_mm'],root_tensile_mpa_per_n_mm=peak_tension['tensile_mpa_per_n_mm'],
            peak_root_von_mises_location_mm=[peak_vm['x_mm'],peak_vm['y_mm']],peak_root_tensile_location_mm=[peak_tension['x_mm'],peak_tension['y_mm']],
            maximum_displacement_mm_per_n_mm=float(np.linalg.norm(u.reshape(-1,2),axis=1).max()),
            compliance_per_n_mm=float(2*solved['strain_energy_n_mm'][column]),
            domain_gauss_von_mises_mpa_per_n_mm=float(domain_vm.max()),
            force_resultant_n_per_n_mm=force.sum(axis=0).tolist(),
            relative_equation_residual=float(solved['relative_equation_residual'][column]),
            force_balance_n=solved['force_balance_n'][:,column].tolist(),moment_balance_n_mm=float(solved['moment_balance_n_mm'][column]))
        if keep_fields:response.update(root_curve=rows,displacement_mm_per_n_mm=u.reshape(-1,2).tolist(),element_von_mises_mpa_per_n_mm=domain_vm.tolist())
        responses.append(response)
    result=dict(refinement=refinement,sector_teeth=mesh['sector_teeth'],nodes=len(mesh['nodes']),elements=len(mesh['elements']),
        minimum_scaled_jacobian=system.minimum_scaled_jacobian,maximum_jacobian_condition=system.maximum_jacobian_condition,responses=responses)
    if keep_fields:result['mesh']=dict(nodes_mm=mesh['nodes'].tolist(),elements=mesh['elements'].tolist(),fixed_node_indices=np.unique(mesh['fixed_dofs']//2).tolist())
    return result


def root_report_html(result):
    esc=lambda value:html.escape(str(value))
    fmt=lambda value:'Unassessed' if value is None else f'{value:.7g}'
    verdict=lambda value:'Unassessed' if value is None else 'Meets entered comparison' if value else 'Unresolved — comparison exceeded'
    limit=lambda value:'Unassessed' if value is None else 'Below entered limit' if value else 'Calculated above entered limit'
    cases=''
    for case in result['cases']:
        rows=''.join(f"<tr><td>{fmt(p['position_fraction'])}</td><td>{fmt(p['root_von_mises_mpa'])}</td><td>{fmt(p['root_tensile_mpa'])}</td><td>{fmt(p['maximum_displacement_mm'])}</td><td>{fmt(p['domain_gauss_von_mises_mpa'])}</td><td>{limit(p['root_within_entered_elastic_limit'])}</td><td>{limit(p['domain_gauss_within_entered_elastic_limit'])}</td></tr>" for p in case['positions'])
        cases+=f"<h3>{esc(case['name'])} — {esc(case['flank'])} flank</h3><p>Ideal applied member torque: {fmt(case['ideal_applied_member_torque_n_mm'])} N mm.</p>"
        cases+='<ul>'+''.join(f'<li>{esc(f)}</li>' for f in case['findings'])+'</ul>'
        if rows:cases+='<table><tr><th>Path fraction</th><th>Root von Mises MPa</th><th>Root tensile principal MPa</th><th>Maximum displacement mm</th><th>Domain Gauss maximum MPa</th><th>Root elastic limit</th><th>Domain elastic limit</th></tr>'+rows+'</table>'
        else:cases+='<p>No assessed operating-case stress result.</p>'
    meshes=''.join(f"<tr><td>{m['refinement']}</td><td>{m['sector_teeth']}</td><td>{m['nodes']}</td><td>{m['elements']}</td><td>{fmt(m['minimum_scaled_jacobian'])}</td><td>{fmt(max(r['relative_equation_residual'] for r in m['responses']))}</td></tr>" for m in result['mesh_levels'])
    changes=''
    if result['calculation_available']:
        for pair_index,rows in enumerate(result['mesh_changes_percent']):
            for response,row in zip(result['mesh_levels'][-1]['responses'],rows,strict=True):
                changes+=f"<tr><td>{pair_index+1} to {pair_index+2}</td><td>{fmt(response['position_fraction'])}, {response['flank']}</td><td>{fmt(row['root_von_mises_mpa_per_n_mm'])}</td><td>{fmt(row['root_tensile_mpa_per_n_mm'])}</td><td>{fmt(row['compliance_per_n_mm'])}</td></tr>"
    domain='<p>Wider-sector comparison unavailable.</p>'
    if result['domain_check']:
        d=result['domain_check'];rows=''
        for response,row in zip(d['responses'],d['changes_percent'],strict=True):
            rows+=f"<tr><td>{fmt(response['position_fraction'])}, {response['flank']}</td><td>{fmt(row['root_von_mises_mpa_per_n_mm'])}</td><td>{fmt(row['root_tensile_mpa_per_n_mm'])}</td><td>{fmt(row['compliance_per_n_mm'])}</td></tr>"
        domain=f"<p>Wider sector: {d['sector_teeth']} teeth; {d['elements']} elements. The support radius is unchanged.</p><table><tr><th>Position and flank</th><th>Root von Mises change %</th><th>Tensile change %</th><th>Compliance change %</th></tr>{rows}</table>"
    findings=''.join(f'<li>{esc(f)}</li>' for f in result['findings']);limits=''.join(f'<li>{esc(f)}</li>' for f in result['limitations'])
    return ('<!doctype html><html><head><meta charset="utf-8"><title>Tooth-root elastic study</title>'
        '<style>body{font-family:Arial,sans-serif;margin:24px;max-width:1400px}table{border-collapse:collapse}td,th{border:1px solid #999;padding:6px}pre{white-space:pre-wrap}</style></head><body>'
        f"<h1>{esc(result['inputs']['name'])}</h1><p><strong>Elastic stress study — no production gearbox rating or fatigue life</strong></p><p>GearForge {esc(result['app_version'])}; method {esc(result['method'])}.</p>"
        f"<p>Material evidence: {esc(result['inputs']['material_status'])}. Mesh refinement: {verdict(result['mesh_convergence_passed'])}. Sector sensitivity: {verdict(result['domain_sensitivity_passed'])}.</p>"
        '<p>Stresses cover the sampled load positions only. Numerical comparisons do not qualify the physical support, material, loading or manufacturing process.</p>'
        f'<ul>{findings}</ul><h2>Operating-case results</h2>{cases}<h2>Mesh checks</h2><table><tr><th>Refinement</th><th>Teeth</th><th>Nodes</th><th>Q9 elements</th><th>Minimum scaled Jacobian</th><th>Equation residual</th></tr>{meshes}</table>'
        f'<p>The final refinement must meet the entered percentage threshold and improve on the earlier change, for both root measures and compliance at every sampled position/flank.</p><table><tr><th>Levels</th><th>Position and flank</th><th>Root von Mises change %</th><th>Tensile change %</th><th>Compliance change %</th></tr>{changes}</table>'
        f'<h2>Cut-face sensitivity</h2>{domain}<h2>Method limits</h2><ul>{limits}</ul>'
        '<h2>Exported fields</h2><p>Calculation JSON retains all unit-torque field bases and operating-case scales. Root-curve CSV values are explicitly per N mm of torque. Case-stress CSV values are actual calculated operating-case stresses. VTK contains the fine mesh; when an operating case is calculable, it shows the first such case at its first sampled position. The calculation records that selection.</p>'
        f"<h2>Complete inputs</h2><pre>{esc(json.dumps(result['inputs'],indent=2,allow_nan=False))}</pre><p>Input fingerprint: {result['study_sha256']}</p></body></html>")


def root_mesh_vtk(result):
    if not result['calculation_available']:raise ValueError('No elastic mesh is available')
    fine=result['mesh_levels'][-1];mesh=fine['mesh'];points=mesh['nodes_mm'];cells=mesh['elements']
    lines=['# vtk DataFile Version 3.0','GearForge 2D elastic root mesh; units mm N MPa; view selection in calculation.json','ASCII','DATASET UNSTRUCTURED_GRID',f'POINTS {len(points)} double']
    lines.extend(f'{x:.16g} {y:.16g} 0' for x,y in points)
    lines.append(f'CELLS {len(cells)} {10*len(cells)}');lines.extend('9 '+' '.join(map(str,cell)) for cell in cells)
    lines.append(f'CELL_TYPES {len(cells)}');lines.extend('28' for _ in cells)
    lines.extend([f'POINT_DATA {len(points)}','SCALARS fixed_support int 1','LOOKUP_TABLE default'])
    fixed=set(mesh['fixed_node_indices']);lines.extend('1' if i in fixed else '0' for i in range(len(points)))
    selection=result.get('mesh_export_view')
    if selection:
        response=fine['responses'][selection['unit_response_index']];scale=selection['torque_magnitude_n_mm']
        lines.append('VECTORS displacement_mm double')
        lines.extend(f'{x*scale:.16g} {y*scale:.16g} 0' for x,y in response['displacement_mm_per_n_mm'])
        lines.extend([f'CELL_DATA {len(cells)}','SCALARS gauss_von_mises_mpa double 1','LOOKUP_TABLE default'])
        lines.extend(f'{v*scale:.16g}' for v in response['element_von_mises_mpa_per_n_mm'])
    return '\n'.join(lines)+'\n'


def root_csv_files(result):
    case_stream=io.StringIO(newline='');writer=csv.writer(case_stream)
    writer.writerow(['case','path_fraction','flank','torque_magnitude_n_mm','root_von_mises_mpa','root_tensile_mpa','maximum_displacement_mm','domain_gauss_von_mises_mpa'])
    for case in result['cases']:
        name=case['name']
        if name.lstrip().startswith(('=','+','-','@')) or name.startswith(('\t','\r','\n')):name="'"+name
        for p in case['positions']:
            writer.writerow([name,p['position_fraction'],case['flank'],case['ideal_applied_member_torque_n_mm'],p['root_von_mises_mpa'],p['root_tensile_mpa'],p['maximum_displacement_mm'],p['domain_gauss_von_mises_mpa']])
    curve_stream=io.StringIO(newline='');writer=csv.writer(curve_stream)
    writer.writerow(['unit_response_index','path_fraction','flank','unit_torque_n_mm','tooth_index','x_mm','y_mm','sigma_x_mpa_per_n_mm','sigma_y_mpa_per_n_mm','tau_xy_mpa_per_n_mm','sigma_z_mpa_per_n_mm','von_mises_mpa_per_n_mm','tensile_mpa_per_n_mm'])
    for index,response in enumerate(result['mesh_levels'][-1]['responses']):
        for row in response['root_curve']:
            writer.writerow([index,response['position_fraction'],response['flank'],response['unit_torque_n_mm'],row['tooth_index'],row['x_mm'],row['y_mm'],*row['stress_mpa_per_n_mm'],row['von_mises_mpa_per_n_mm'],row['tensile_mpa_per_n_mm']])
    return case_stream.getvalue(),curve_stream.getvalue()


def export_root_study(study,destination):
    from .maintenance import write_manifest
    result=calculate_root_study(study);dest=Path(destination).absolute()
    if dest.exists() or dest.is_symlink():raise FileExistsError('Choose a new root-stress assessment directory')
    result['mesh_export_view']=None
    for case_index,case in enumerate(result['cases']):
        if case['positions']:
            position=case['positions'][0]
            result['mesh_export_view']=dict(case_index=case_index,case_name=case['name'],position_fraction=position['position_fraction'],
                unit_response_index=position['unit_response_index'],torque_magnitude_n_mm=case['ideal_applied_member_torque_n_mm']);break
    dest.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.gearforge-root-',dir=dest.parent) as temporary:
        stage=Path(temporary)/'study';stage.mkdir();study.save(stage/'design.gearforge-root')
        atomic_text(stage/'calculation.json',json.dumps(result,indent=2,allow_nan=False));atomic_text(stage/'report.html',root_report_html(result))
        if result['calculation_available']:
            cases,curves=root_csv_files(result);atomic_text(stage/'case-stresses.csv',cases)
            atomic_text(stage/'root-curves-per-unit-torque.csv',curves);atomic_text(stage/'mesh.vtk',root_mesh_vtk(result))
        manifest=write_manifest(stage,kind='gearforge-root-stress',method=METHOD,study_sha256=result['study_sha256'],production_approved=False)
        if dest.exists() or dest.is_symlink():raise FileExistsError('Root-stress output already exists')
        stage.rename(dest)
    return dict(destination=str(dest),files=len(manifest['files'])+1,study_sha256=result['study_sha256'],
        calculation_available=result['calculation_available'],production_approved=False)


def relative_changes(first,second):
    fields=('root_von_mises_mpa_per_n_mm','root_tensile_mpa_per_n_mm','compliance_per_n_mm')
    return [{key:100*abs(b[key]-a[key])/max(abs(b[key]),1e-30) for key in fields}
        for a,b in zip(first['responses'],second['responses'],strict=True)]


def calculate_root_study(study):
    study.validate();inputs=asdict(study)
    digest=hashlib.sha256(json.dumps(inputs,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
    source=calculate_profile_study(study.source)
    result=dict(schema_version=1,app_version=__version__,method=METHOD,inputs=inputs,study_sha256=digest,
        source_profile_sha256=source['study_sha256'],calculation_available=False,mesh_levels=[],domain_check=None,
        mesh_convergence_passed=None,domain_sensitivity_passed=None,cases=[],findings=list(source['findings']),
        production_approved=False,rated_output_torque_nm=None,rated_gearbox_life_hours=None,
        limitations=[
            'Homogeneous isotropic small-strain linear elasticity of a uniform-width 2D sector; plane stress or plane strain is explicit. No 3D face-edge effects, plasticity, residual stress, anisotropy or fatigue life.',
            'The inner arc is fully fixed; radial cut faces are traction-free. The wider-sector check varies cut-face proximity only, not the validity of the actual hub/shaft support assumption.',
            'Load positions are sampled fractions of the nominal ideal active path, not a continuous maximum over mesh engagement. Material/contact distribution, mesh stiffness sharing and dynamics are not solved.',
            'A smooth parabolic pressure patch on the involute is normalized to the retained ideal member torque. Its width and factors must be established; it is not a solved Hertz/contact pressure distribution.',
            'Q9 displacement elements use full 3x3 integration on bilinear piecewise-straight geometry. Root stress is recovered separately on each adjacent element edge at five positions, without nodal averaging; it is not a mathematically certified continuous peak.',
            'Mesh and wider-sector comparisons indicate sensitivity only. Localized load/support stresses may be singular or unresolved; a stable comparison does not establish physical validity or manufacturing strength.',
            'Material temperature range and elastic limit are declared inputs. Missing factors/temperatures remain incomplete. No production rating or life is approved by a stress result.'])
    for field in ('youngs_modulus_mpa','poisson_ratio','effective_face_width_mm','support_radius_mm','patch_half_width_mm'):
        if getattr(study,field) is None:result['findings'].append('Missing '+field.replace('_',' '))
    if not source['profile_available'] or any(getattr(study,f) is None for f in ('youngs_modulus_mpa','poisson_ratio','effective_face_width_mm','support_radius_mm','patch_half_width_mm')):return result
    if study.material_status!='declared':result['findings'].append('Elastic material data are '+study.material_status+'.')
    if not study.material_reference.strip() or not study.redistribution_basis.strip():result['findings'].append('Material source and redistribution basis are incomplete.')
    if not study.support_basis.strip():result['findings'].append('The support and plane-model basis is missing.')
    try:
        profile=RackProfile(study.source);patches=load_patches(study,profile)
        levels=[solve_root_mesh(study,profile,patches,refinement,keep_fields=refinement==4) for refinement in (1,2,4)]
        changes=[relative_changes(a,b) for a,b in zip(levels,levels[1:])]
        # Compare the final refinement at the entered tolerance and require a
        # decreasing change from the coarser pair. The coarse mesh is a trend
        # diagnostic; none of these comparisons is an error-bound certificate.
        passed=all(last[key]<=study.convergence_tolerance_percent and last[key]<=max(first[key],1e-8)
            for first,last in zip(changes[0],changes[1],strict=True) for key in last)
        result.update(calculation_available=True,mesh_levels=levels,mesh_changes_percent=changes,mesh_convergence_passed=passed,load_patches=patches)
        if not passed:result['findings'].append('Final root-stress/compliance mesh changes exceed tolerance or are not decreasing; refine before interpreting stresses.')
        wider=study.sector_teeth+2
        if wider<profile.z and wider<=11:
            try:
                domain=solve_root_mesh(study,profile,patches,4,sector_teeth=wider)
                change=relative_changes(levels[-1],domain)
                domain_passed=all(v<=study.convergence_tolerance_percent for row in change for v in row.values())
                result['domain_check']=dict(**domain,changes_percent=change);result['domain_sensitivity_passed']=domain_passed
                if not domain_passed:result['findings'].append('Root stress/compliance remains sensitive to sector width; the cut-face domain is not established.')
            except (ValueError,OverflowError) as exc:
                result['findings'].append('Wider-sector comparison unavailable: '+str(exc))
        else:result['findings'].append('No wider-sector comparison is available within this domain; boundary sensitivity remains unassessed.')
    except (ValueError,OverflowError) as exc:
        result.update(calculation_available=False,mesh_levels=[],domain_check=None,mesh_convergence_passed=None,domain_sensitivity_passed=None)
        result['findings'].append(str(exc));return result
    fine=result['mesh_levels'][-1]
    role=study.source.role;ratio=study.source.source.pair.wheel_teeth/study.source.source.pair.pinion_teeth
    loads={c.case_name:c for c in study.cases}
    for duty in study.source.source.duty:
        case=loads[duty.name];reason=[]
        if case.normal_load_multiplier is None or case.load_share is None:reason.append('Mesh load multiplier and sharing must be entered')
        temperature_supported=None
        if None not in (case.temperature_c,study.minimum_temperature_c,study.maximum_temperature_c):
            temperature_supported=study.minimum_temperature_c<=case.temperature_c<=study.maximum_temperature_c
            if not temperature_supported:reason.append('Temperature is outside the declared elastic material range')
        else:reason.append('Material temperature coverage is unassessed')
        if not case.factor_basis.strip():reason.append('Load distribution/factor basis is missing')
        torque=None if case.normal_load_multiplier is None or case.load_share is None else abs(duty.input_torque_nm)*1000*(ratio if role=='wheel' else 1)*case.normal_load_multiplier*case.load_share
        # Positive pinion driving torque has an opposing mesh torque. The
        # driven wheel's ideal mesh torque is positive in its local frame.
        direction=duty.input_torque_nm*(1 if role=='wheel' else -1)
        flank='right' if direction>=0 else 'left';positions=[]
        if torque is not None and temperature_supported is not False:
            for index,response in enumerate(fine['responses']):
                if response['flank']!=flank:continue
                peak=response['root_von_mises_mpa_per_n_mm']*torque;domain_vm=response['domain_gauss_von_mises_mpa_per_n_mm']*torque
                positions.append(dict(position_fraction=response['position_fraction'],unit_response_index=index,
                    root_von_mises_mpa=peak,root_tensile_mpa=response['root_tensile_mpa_per_n_mm']*torque,
                    maximum_displacement_mm=response['maximum_displacement_mm_per_n_mm']*torque,
                    strain_energy_n_mm=.5*response['compliance_per_n_mm']*torque*torque,
                    domain_gauss_von_mises_mpa=domain_vm,
                    root_within_entered_elastic_limit=None if study.maximum_elastic_stress_mpa is None else peak<=study.maximum_elastic_stress_mpa,
                    domain_gauss_within_entered_elastic_limit=None if study.maximum_elastic_stress_mpa is None else domain_vm<=study.maximum_elastic_stress_mpa))
        result['cases'].append(dict(name=duty.name,flank=flank,ideal_applied_member_torque_n_mm=torque,
            material_temperature_supported=temperature_supported,positions=positions,findings=reason,
            evidence_complete=bool(study.material_status=='declared' and study.material_reference.strip()
                and study.redistribution_basis.strip() and study.support_basis.strip()
                and study.maximum_elastic_stress_mpa is not None and not reason),
            numerical_checks_passed=result['mesh_convergence_passed'] is True and result['domain_sensitivity_passed'] is True))
    return result
