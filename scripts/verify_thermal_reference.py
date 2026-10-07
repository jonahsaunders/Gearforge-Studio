"""Compare original thermal networks with independent SciPy Radau integration.

The reference assembles heat flows directly from the declared topology in a
separate process. It does not import GearForge's matrices, modes or root isolator.
No third-party code or property/loss data is copied into the application.
"""
from dataclasses import asdict
import argparse
import json
import math
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from gearforge.thermal import (AMBIENT,ThermalNode,ThermalLink,ThermalPhase,ThermalStudy,
    synthetic_thermal_example,calculate_thermal_study)
from gearforge.models import atomic_text

ADAPTER=r'''
import json,sys
import numpy as np
import scipy
from scipy.integrate import solve_ivp
from scipy.optimize import root

def run_phase(study,phase,initial,times):
    names=[node['name'] for node in study['nodes']];index={name:i for i,name in enumerate(names)}
    capacity=[node['capacity_j_per_k'] for node in study['nodes']]
    def derivative(t,values):
        heat=[phase['heat_w'][name] for name in names];rejected=0.
        for link in study['links']:
            i=index[link['first']];g=phase['conductance_w_per_k'][link['name']]
            if link['second']=='Ambient':
                flow=g*(values[i]-phase['ambient_c']);heat[i]-=flow;rejected+=flow
            else:
                j=index[link['second']];flow=g*(values[i]-values[j]);heat[i]-=flow;heat[j]+=flow
        return [heat[i]/capacity[i] for i in range(len(names))]+[rejected]
    duration=phase['duration_s'];start=[*initial,0.]
    if duration:
        solution=solve_ivp(derivative,(0,duration),start,method='Radau',rtol=2e-11,atol=1e-10,dense_output=True)
        if not solution.success:raise RuntimeError(solution.message)
        values=solution.sol(times);end=solution.y[:,-1]
    else:values=np.array(start)[:,None];end=np.array(start)
    return dict(temperature_c=values[:-1].T.tolist(),end=end[:-1].tolist(),
        generated_j=sum(phase['heat_w'].values())*duration,rejected_j=float(end[-1]),
        stored_j=sum(c*(b-a) for c,a,b in zip(capacity,initial,end[:-1])))

outputs=[]
for request in json.load(sys.stdin):
    study=request['study'];initial=[node['initial_temperature_c'] for node in study['nodes']]
    rows=[]
    for phase,times in zip(study['phases'],request['entered_times']):
        row=run_phase(study,phase,initial,times);rows.append(row);initial=row['end']
    periodic=None
    if request['periodic_reference']:
        def residual(initial):
            state=list(initial)
            for phase in study['phases']:state=run_phase(study,phase,state,[phase['duration_s']])['end']
            return np.array(state)-initial
        solution=root(residual,[study['phases'][0]['ambient_c']]*len(study['nodes']),tol=1e-9)
        if max(abs(residual(solution.x)))>2e-7:raise RuntimeError('Reference shooting closure did not converge')
        state=solution.x;periodic=[]
        for phase,times in zip(study['phases'],request['periodic_times']):
            row=run_phase(study,phase,state,times);periodic.append(row);state=row['end']
    outputs.append(dict(entered=rows,periodic=periodic))
print(json.dumps(dict(scipy_version=scipy.__version__,results=outputs),allow_nan=False))
'''


def fixtures():
    studies=[];base=synthetic_thermal_example();studies.append(('Original running/cooling cycle',base,True))
    mixed=ThermalStudy.from_dict(asdict(base));mixed.nodes[0].initial_temperature_c=110;mixed.nodes[1].initial_temperature_c=5
    studies.append(('Mixed initial temperatures and internal maxima',mixed,True))
    one=ThermalStudy.from_dict(asdict(base));one.nodes=[ThermalNode('Body',1000,20)];one.links=[ThermalLink('Cooling','Body',AMBIENT)]
    one.phases=[ThermalPhase('Heat',one.source.duty[0].name,500,20,{'Body':100},{'Cooling':2})]
    studies.append(('Analytical one-body heating',one,True))
    insulated=ThermalStudy.from_dict(asdict(one));insulated.phases[0].conductance_w_per_k['Cooling']=0
    studies.append(('Insulated temperature drift',insulated,False))
    exchange=ThermalStudy.from_dict(asdict(one));exchange.nodes=[ThermalNode('Hot',1000,100),ThermalNode('Cold',3000,20)]
    exchange.links=[ThermalLink('Exchange','Hot','Cold')]
    exchange.phases=[ThermalPhase('Equalize',exchange.source.duty[0].name,100000,20,{'Hot':0,'Cold':0},{'Exchange':5})]
    studies.append(('Insulated exchange and unequal capacities',exchange,False))
    stiff=ThermalStudy.from_dict(asdict(base));stiff.nodes[0].capacity_j_per_k=10;stiff.nodes[2].capacity_j_per_k=100000
    stiff.phases[0].conductance_w_per_k['Gears to oil']=40
    studies.append(('Separated thermal time constants',stiff,True))
    long=ThermalStudy.from_dict(asdict(base));long.phases=long.phases[:1];long.phases[0].duration_s=36000000
    studies.append(('Ten-thousand-hour constant operation',long,True))
    parallel=ThermalStudy.from_dict(asdict(base));parallel.nodes.append(ThermalNode('Bearing',350,80))
    parallel.links.extend([ThermalLink('Bearing to housing','Bearing','Housing'),ThermalLink('Bearing to air','Bearing',AMBIENT)])
    for phase in parallel.phases:
        phase.heat_w['Bearing']=2;phase.conductance_w_per_k.update({'Bearing to housing':1.2,'Bearing to air':.1})
    studies.append(('Extra bearing body and parallel cooling branches',parallel,True))
    return studies


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reference-python',type=Path,default=Path(sys.executable))
    parser.add_argument('--out',type=Path,default=ROOT/'build/thermal-reference-comparison.json')
    parser.add_argument('--write-fixture',type=Path);args=parser.parse_args()
    records=[];requests=[];actual=[]
    for name,study,periodic in fixtures():
        result=calculate_thermal_study(study)
        if periodic and result['periodic_cycle'] is None:raise RuntimeError(result['findings'])
        request=dict(study=asdict(study),periodic_reference=periodic,
            entered_times=[[p['time_s'] for p in row['profile']] for row in result['phases']],
            periodic_times=[] if not periodic else [[p['time_s'] for p in row['profile']] for row in result['periodic_cycle']['phases']])
        requests.append(request);actual.append(result);records.append(dict(name=name,**request))
    process=subprocess.run([str(args.reference_python),'-c',ADAPTER],input=json.dumps(requests),capture_output=True,text=True,timeout=180)
    if process.returncode:raise RuntimeError(process.stderr[-6000:])
    reference=json.loads(process.stdout);comparisons=0;failures=[];max_temp_error=0.;max_energy_relative=0.
    for record,result,expected in zip(records,actual,reference['results'],strict=True):
        record['expected']=expected
        for key,rows in (('entered',result['phases']),('periodic',[] if result['periodic_cycle'] is None else result['periodic_cycle']['phases'])):
            for i,(row,ref) in enumerate(zip(rows,expected[key] or [],strict=True)):
                for j,(point,temperatures) in enumerate(zip(row['profile'],ref['temperature_c'],strict=True)):
                    for name,value in zip(point['temperature_c'],temperatures):
                        got=point['temperature_c'][name];comparisons+=1;max_temp_error=max(max_temp_error,abs(got-value))
                        if not math.isclose(got,value,rel_tol=2e-9,abs_tol=2e-7):failures.append(dict(case=record['name'],cycle=key,phase=i,sample=j,body=name,actual=got,expected=value))
                for field,reference_field in (('heat_generated_j','generated_j'),('heat_rejected_to_ambient_j','rejected_j'),('stored_energy_change_j','stored_j')):
                    got=row[field];value=ref[reference_field];comparisons+=1
                    if abs(value)>1e-5:max_energy_relative=max(max_energy_relative,abs((got-value)/value))
                    if not math.isclose(got,value,rel_tol=2e-8,abs_tol=2e-5):failures.append(dict(case=record['name'],cycle=key,phase=i,field=field,actual=got,expected=value))
    report=dict(reference='https://docs.scipy.org/doc/scipy/reference/generated/scipy.integrate.solve_ivp.html',reference_method='SciPy Radau integration and independent shooting closure',
        reference_version=reference['scipy_version'],reference_license='BSD-3-Clause',
        provenance='Original GearForge thermal topology, inputs and reference adapter. Separate direct heat-flow ODE; no GearForge matrices, modes or root isolator in the reference process.',
        scope='Temperatures at display/critical times and generated, rejected and stored energy for entered and independently solved periodic cycles in eight original networks. No physical loss, cooling or material qualification.',
        comparisons=comparisons,maximum_temperature_absolute_error_c=max_temp_error,maximum_energy_relative_error=max_energy_relative,
        tolerance=dict(temperature=dict(relative=2e-9,absolute_c=2e-7),energy=dict(relative=2e-8,absolute_j=2e-5)),
        passed=not failures,failures=failures,cases=records)
    atomic_text(args.out,json.dumps(report,indent=2,allow_nan=False))
    if args.write_fixture:
        if failures:raise SystemExit('Comparison failed; fixture not written')
        atomic_text(args.write_fixture,json.dumps(report,indent=2,allow_nan=False))
    print(json.dumps({k:report[k] for k in ('comparisons','maximum_temperature_absolute_error_c','maximum_energy_relative_error','passed','failures')}))
    return int(bool(failures))


if __name__=='__main__':raise SystemExit(main())
