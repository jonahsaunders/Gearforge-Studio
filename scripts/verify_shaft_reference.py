"""Compare shaft results with a separately installed PyNiteFEA 3.2.0 model.

PyNite is an optional MIT-licensed verification tool, not an app dependency.
Fixtures contain scalar outputs for GearForge-authored synthetic cases only.
"""
from dataclasses import asdict
import argparse
import importlib.metadata
import json
import math
import platform
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from gearforge.shafts import ShaftStudy,ShaftSection,ShaftCase,ShaftLoad,solve_shaft_case
from gearforge.models import atomic_text


def reference_cases():
    return [
        ShaftStudy(name="central-force"),
        ShaftStudy(name="asymmetric-point",cases=[ShaftCase(loads=[ShaftLoad(position_mm=30,force_y_n=-137)])]),
        ShaftStudy(name="right-overhang",bearing_a_mm=10,bearing_b_mm=90,
                   cases=[ShaftCase(loads=[ShaftLoad(position_mm=120,force_y_n=-200,force_z_n=90)])]),
        ShaftStudy(name="left-overhang-couple",bearing_a_mm=35,bearing_b_mm=110,
                   cases=[ShaftCase(loads=[ShaftLoad(position_mm=0,force_y_n=45,force_z_n=-76,moment_y_nm=3,moment_z_nm=-2)])]),
        ShaftStudy(name="two-plane-and-couple",cases=[ShaftCase(loads=[
            ShaftLoad(name="load-a",position_mm=35,force_y_n=-100,force_z_n=37,moment_y_nm=.7),
            ShaftLoad(name="load-b",position_mm=85,force_y_n=40,force_z_n=-90,moment_z_nm=1.3)])]),
        ShaftStudy(name="end-couple",cases=[ShaftCase(loads=[ShaftLoad(position_mm=120,moment_z_nm=1)])]),
        ShaftStudy(name="stepped-solid",sections=[ShaftSection(end_mm=40,outer_diameter_mm=16),
            ShaftSection(start_mm=40,end_mm=120,outer_diameter_mm=10,youngs_modulus_mpa=70000,shear_modulus_mpa=70000/2.6)],
            cases=[ShaftCase(loads=[ShaftLoad(position_mm=75,force_y_n=-143,force_z_n=52)])]),
        ShaftStudy(name="stepped-hollow-overhang",bearing_a_mm=15,bearing_b_mm=95,
            sections=[ShaftSection(end_mm=50,outer_diameter_mm=20,inner_diameter_mm=8),
                      ShaftSection(start_mm=50,end_mm=100,outer_diameter_mm=16,inner_diameter_mm=6),
                      ShaftSection(start_mm=100,end_mm=120,outer_diameter_mm=12,inner_diameter_mm=4)],
            cases=[ShaftCase(loads=[ShaftLoad(position_mm=65,force_y_n=-300,force_z_n=40,moment_z_nm=.8),
                                  ShaftLoad(name="overhung",position_mm=120,force_y_n=30,force_z_n=-60)])]),
        ShaftStudy(name="axial-torsion-hollow",bearing_a_mm=15,bearing_b_mm=105,
            sections=[ShaftSection(end_mm=50,outer_diameter_mm=20,inner_diameter_mm=8),
                      ShaftSection(start_mm=50,end_mm=120,outer_diameter_mm=16,inner_diameter_mm=6)],
            cases=[ShaftCase(loads=[ShaftLoad(name='input',position_mm=0,torque_nm=3),
                ShaftLoad(name='mesh',position_mm=70,force_y_n=-100,force_z_n=80,axial_n=250,torque_nm=-3,moment_z_nm=-5)])]),
    ]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,default=ROOT/'build/shaft-reference-comparison.json')
    parser.add_argument('--write-fixture',type=Path)
    args=parser.parse_args()
    from Pynite import FEModel3D
    import numpy
    version=importlib.metadata.version('PyNiteFEA')
    if version!='3.2.0':raise SystemExit('Use the pinned PyNiteFEA 3.2.0 reference')
    if tuple(map(int,numpy.__version__.split('.')[:2]))<(2,4):
        raise SystemExit('The reference requires its separate NumPy >=2.4 environment')
    fixtures=[];failures=[];maximum_error=0;comparisons=0
    for study in reference_cases():
        actual=solve_shaft_case(study)
        expected=[]
        reference=FEModel3D()
        points={point['position_mm']:point for point in actual['samples']}
        positions=sorted(points)
        names={position:f'N{i}' for i,position in enumerate(positions)}
        for position in positions:
            name=names[position];reference.add_node(name,position,0,0)
            support=position in (study.bearing_a_mm,study.bearing_b_mm)
            locator=study.bearing_a_mm if study.axial_locator=='a' else study.bearing_b_mm
            reference.def_support(name,support_DX=position==locator,support_DY=support,support_DZ=support,
                                  support_RX=position==0)
        for index,section in enumerate(study.sections):
            # Independently define the reference's area and flexural/torsional
            # properties; no GearForge section-property method is called.
            d,di=section.outer_diameter_mm,section.inner_diameter_mm
            inertia=math.pi*(d**4-di**4)/64
            reference.add_material(f'material{index}',E=section.youngs_modulus_mpa,G=section.shear_modulus_mpa,
                nu=section.youngs_modulus_mpa/(2*section.shear_modulus_mpa)-1,rho=0)
            reference.add_section(f'section{index}',A=math.pi*(d*d-di*di)/4,Iy=inertia,Iz=inertia,J=2*inertia)
        for index,(start,end) in enumerate(zip(positions,positions[1:])):
            section_index=next(i for i,s in enumerate(study.sections) if s.start_mm<=start and s.end_mm>=end)
            reference.add_member(f'M{index}',names[start],names[end],f'material{section_index}',f'section{section_index}')
        for load in study.cases[0].loads:
            for direction,field,scale in (('FX','axial_n',1),('FY','force_y_n',1),('FZ','force_z_n',1),
                                          ('MX','torque_nm',1000),('MY','moment_y_nm',1000),('MZ','moment_z_nm',1000)):
                if getattr(load,field):reference.add_node_load(names[load.position_mm],direction,getattr(load,field)*scale,case='load')
        reference.add_load_combo('case',{'load':1})
        reference.analyze_linear(log=False)
        for index,position in enumerate((study.bearing_a_mm,study.bearing_b_mm)):
            node=reference.nodes[names[position]]
            for plane in ('x','y','z'):
                value=float(getattr(node,'RxnF'+plane.upper())['case'])
                got=actual['bearings'][index][f'reaction_on_shaft_{plane}_n']
                expected.append(dict(kind='reaction',bearing_index=index,plane=plane,value=value))
                comparisons+=1;maximum_error=max(maximum_error,abs(got-value))
                if not math.isclose(got,value,rel_tol=1e-8,abs_tol=1e-8):failures.append(dict(case=study.name,quantity='reaction',actual=got,expected=value))
        for position,point in points.items():
            node=reference.nodes[names[position]]
            for field,attribute,sign in (('deflection_y_mm','DY',1),('deflection_z_mm','DZ',1),
                ('slope_y_rad','RZ',1),('slope_z_rad','RY',-1),('axial_displacement_mm','DX',1),('twist_rad','RX',1)):
                value=sign*float(getattr(node,attribute)['case'])
                if not math.isfinite(value):raise ValueError(f'Reference undefined: {study.name}, {field}, {position}')
                got=point[field]
                expected.append(dict(kind='point',field=field,position_mm=position,value=value))
                comparisons+=1;maximum_error=max(maximum_error,abs(got-value))
                if not math.isclose(got,value,rel_tol=1e-8,abs_tol=1e-8):failures.append(dict(case=study.name,quantity=field,position_mm=position,actual=got,expected=value))
        fixtures.append(dict(name=study.name,study=asdict(study),expected=expected))
    report=dict(reference='https://github.com/JWock82/Pynite',reference_version=version,reference_license='MIT',
        runtime=dict(python=platform.python_version(),numpy=numpy.__version__,scipy=importlib.metadata.version('scipy')),
        method='PyNiteFEA 3D elastic beam finite elements via its public API; original GearForge inputs and adapter',
        scope='Three-axis support reactions, bending deflection/slope, axial displacement and twist for point forces/couples, overhangs, hollow/solid stepped sections; not fatigue or bearing life',
        tolerance=dict(relative=1e-8,absolute=1e-8),comparisons=comparisons,maximum_absolute_error=maximum_error,
        failures=failures,passed=not failures,cases=fixtures)
    atomic_text(args.out,json.dumps(report,indent=2,allow_nan=False))
    if args.write_fixture:
        if failures:raise SystemExit('Reference comparison failed; fixture not published')
        atomic_text(args.write_fixture,json.dumps(report,indent=2,allow_nan=False))
    print(json.dumps({key:report[key] for key in ('comparisons','maximum_absolute_error','passed','failures')}))
    return int(bool(failures))


if __name__=='__main__':raise SystemExit(main())
