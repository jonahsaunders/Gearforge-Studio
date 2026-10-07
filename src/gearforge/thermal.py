"""Original passive lumped thermal networks, exact within piecewise-linear inputs.

No inferred heat-transfer coefficients, loss maps or material property tables.
Capacity-weighted symmetric modes give transient temperature and energy integrals.
Continuous extrema are isolated from exponential sums, not drawing samples.
"""
from __future__ import annotations

from dataclasses import asdict,dataclass,field
import hashlib
import html
import json
import math
from pathlib import Path
import tempfile

import numpy as np

from . import __version__
from .bearings import optional_number
from .engineering import DutyPoint,EngineeringStudy,_integer,_model,_text,calculate_study
from .models import atomic_text,finite,read_text_limited,strict_json

METHOD='passive-thermal-network-1'
MAX_BYTES=3_000_000
AMBIENT='Ambient'


@dataclass
class ThermalNode:
    name: str = 'Gear train'
    capacity_j_per_k: float | None = None
    initial_temperature_c: float | None = None
    minimum_allowable_c: float | None = None
    maximum_allowable_c: float | None = None
    model_minimum_c: float | None = None
    model_maximum_c: float | None = None
    data_status: str = 'unverified'
    source_reference: str = ''
    redistribution_basis: str = ''

    def validate(self):
        _text(self.name,'Thermal body name',100,required=True)
        if self.name==AMBIENT:raise ValueError('Ambient is reserved for the external heat bath')
        if self.data_status not in ('unverified','synthetic','declared'):raise ValueError('Invalid thermal input provenance')
        for key in ('source_reference','redistribution_basis'):_text(getattr(self,key),key,4000)
        self.capacity_j_per_k=optional_number(self.capacity_j_per_k,'Thermal capacity J/K',.001,1e9)
        for key in ('initial_temperature_c','minimum_allowable_c','maximum_allowable_c','model_minimum_c','model_maximum_c'):
            setattr(self,key,optional_number(getattr(self,key),key,-100,1000))
        for lo,hi in ((self.minimum_allowable_c,self.maximum_allowable_c),(self.model_minimum_c,self.model_maximum_c)):
            if lo is not None and hi is not None and lo>hi:raise ValueError('Thermal temperature bounds are reversed')


@dataclass
class ThermalLink:
    name: str = 'Gears to oil'
    first: str = 'Gear train'
    second: str = 'Oil'

    def validate(self,names):
        _text(self.name,'Thermal path name',100,required=True)
        if self.first not in names or self.second not in names|{AMBIENT} or self.first==self.second:
            raise ValueError('Each thermal path joins distinct defined bodies, or a body to Ambient')


@dataclass
class ThermalPhase:
    name: str = 'Continuous rated-input target'
    source_case: str = 'Continuous rated-input target'
    duration_s: float = 36000000.0
    ambient_c: float | None = None
    heat_w: dict[str,float | None] = field(default_factory=dict)
    conductance_w_per_k: dict[str,float | None] = field(default_factory=dict)
    loss_basis: str = ''
    cooling_basis: str = ''

    def validate(self,names,links,source_names):
        _text(self.name,'Thermal phase name',120,required=True)
        if self.source_case not in source_names:raise ValueError('Each thermal phase must name a retained operating case')
        self.duration_s=finite(self.duration_s,'Thermal phase duration seconds',0,1e12)
        self.ambient_c=optional_number(self.ambient_c,'Thermal phase ambient',-100,1000)
        for key,expected,upper in (('heat_w',names,1e7),('conductance_w_per_k',links,1e6)):
            values=getattr(self,key)
            if not isinstance(values,dict) or set(values)!=expected:raise ValueError(f'{key} must cover each thermal body/path exactly once')
            setattr(self,key,{name:optional_number(value,f'{key}: {name}',0,upper) for name,value in values.items()})
        for key in ('loss_basis','cooling_basis'):_text(getattr(self,key),key,10000)


@dataclass
class ThermalStudy:
    name: str = 'Gearbox thermal study'
    source: EngineeringStudy = field(default_factory=EngineeringStudy)
    nodes: list[ThermalNode] = field(default_factory=lambda:[ThermalNode(),ThermalNode(name='Oil'),ThermalNode(name='Housing')])
    links: list[ThermalLink] = field(default_factory=lambda:[ThermalLink(),ThermalLink('Oil to housing','Oil','Housing'),ThermalLink('Housing to ambient','Housing',AMBIENT)])
    phases: list[ThermalPhase] = field(default_factory=lambda:[ThermalPhase(
        heat_w={'Gear train':None,'Oil':None,'Housing':None},
        conductance_w_per_k={'Gears to oil':None,'Oil to housing':None,'Housing to ambient':None})])
    sequence_basis: str = ''
    notes: str = 'Each body has uniform temperature. Losses and linear conductances are constant within each phase and need applicable evidence.'
    schema_version: int = 1

    def validate(self):
        _integer(self.schema_version,'Thermal schema',1,1)
        _text(self.name,'Thermal study name',1000,required=True)
        for key in ('sequence_basis','notes'):_text(getattr(self,key),key,10000)
        if not isinstance(self.source,EngineeringStudy):raise ValueError('Retained engineering study required')
        self.source.validate()
        if not isinstance(self.nodes,list) or not 1<=len(self.nodes)<=12:raise ValueError('Define 1..12 thermal bodies')
        for n in self.nodes:
            if not isinstance(n,ThermalNode):raise ValueError('Invalid thermal body')
            n.validate()
        names={n.name for n in self.nodes}
        if len(names)!=len(self.nodes):raise ValueError('Thermal body names must be unique')
        if not isinstance(self.links,list) or len(self.links)>60:raise ValueError('At most 60 thermal paths are supported')
        edges=set()
        for link in self.links:
            if not isinstance(link,ThermalLink):raise ValueError('Invalid thermal path')
            link.validate(names);edge=frozenset((link.first,link.second))
            if edge in edges:raise ValueError('Combine parallel thermal paths into one declared conductance')
            edges.add(edge)
        links={link.name for link in self.links}
        if len(links)!=len(self.links):raise ValueError('Thermal path names must be unique')
        if not isinstance(self.phases,list) or not 1<=len(self.phases)<=200:raise ValueError('Define 1..200 ordered thermal phases')
        for phase in self.phases:
            if not isinstance(phase,ThermalPhase):raise ValueError('Invalid thermal phase')
            phase.validate(names,links,{c.name for c in self.source.duty})
        if len({p.name for p in self.phases})!=len(self.phases):raise ValueError('Thermal phase names must be unique')
        if math.fsum(p.duration_s for p in self.phases)<=0:raise ValueError('The thermal sequence must have positive duration')

    @classmethod
    def from_dict(cls,data):
        if not isinstance(data,dict):raise ValueError('Invalid thermal study')
        data=dict(data)
        for key,model,limit in (('nodes',ThermalNode,12),('links',ThermalLink,60),('phases',ThermalPhase,200)):
            if not isinstance(data.get(key),list) or len(data[key])>limit:raise ValueError(f'Invalid thermal {key}')
            data[key]=[_model(model,row) for row in data[key]]
        data['source']=EngineeringStudy.from_dict(data.get('source'))
        result=_model(cls,data);result.validate();return result

    @classmethod
    def load(cls,path):return cls.from_dict(strict_json(read_text_limited(Path(path),MAX_BYTES,'Thermal study')))

    def save(self,path):
        self.validate();text=json.dumps(asdict(self),indent=2,allow_nan=False)
        if len(text.encode())>MAX_BYTES:raise ValueError('Thermal study exceeds 3 MB')
        atomic_text(Path(path),text)


def thermal_from_study(source):
    source=EngineeringStudy.from_dict(asdict(source));study=ThermalStudy(name=source.name+' — thermal',source=source)
    study.phases=[ThermalPhase(name=p.name,source_case=p.name,duration_s=3600*p.duration_hours,ambient_c=p.ambient_c,
        heat_w={n.name:None for n in study.nodes},conductance_w_per_k={link.name:None for link in study.links}) for p in source.duty]
    study.sequence_basis='Retained duty rows in entered order. Establish actual chronology and repeat pattern; aggregate lifetime exposure is not inherently a thermal cycle.'
    return study


def synthetic_thermal_example():
    study=thermal_from_study(EngineeringStudy());study.name='Synthetic thermal network — no measured loss or cooling data'
    for node,capacity in zip(study.nodes,(1800,3000,4500)):
        node.capacity_j_per_k=capacity;node.initial_temperature_c=25
        node.minimum_allowable_c=0;node.maximum_allowable_c=90;node.model_minimum_c=0;node.model_maximum_c=120
        node.data_status='synthetic';node.source_reference='Original invented GearForge numerical fixture; not measured hardware'
        node.redistribution_basis='Original fixture, Apache-2.0'
    source=study.source.duty[0].name
    stopped='Stopped cooling'
    study.source.duty.append(DutyPoint(name=stopped,input_rpm=0,input_torque_nm=0,duration_hours=5000,ambient_c=25))
    study.source.target_life_hours=15000
    study.phases=[ThermalPhase('Running',source,3600,40,{'Gear train':12.5,'Oil':3,'Housing':1},
        {'Gears to oil':4,'Oil to housing':2,'Housing to ambient':.8},'Invented mesh/bearing/churning heat allocation; no efficiency-derived loss claim','Invented constant conductances'),
        ThermalPhase('Cooling after stop',stopped,1800,25,{n.name:0 for n in study.nodes},
        {'Gears to oil':2,'Oil to housing':1.5,'Housing to ambient':.6},'Zero heat is an explicit illustrative stopped condition; retained case provides context only','Invented stopped conductances')]
    study.sequence_basis='Original 1 h running / 0.5 h cooling example. Repeating it 10,000 times matches the retained 10,000 running hours plus 5,000 stopped hours. It does not establish actual duty coverage or durability.'
    return study


def _phi(rates,time):
    """Integral of exp(-rate*t) and its integral; stable for small arguments."""
    one=[];two=[]
    for rate in rates:
        x=rate*time
        if abs(x)<1e-4:
            one.append(time*(1-x/2+x*x/6-x**3/24+x**4/120))
            two.append(time*time*(.5-x/6+x*x/24-x**3/120+x**4/720))
        else:
            first=-math.expm1(-x)/rate;one.append(first);two.append((time-first)/rate)
    return np.array(one),np.array(two)


def exponential_roots(rates,coefficients,duration):
    """Isolate every zero of a finite real exponential sum on [0,duration].

    Divide by the slowest positive exponential. Its derivative has one fewer
    term. Recursion partitions the original sum into monotone intervals; each
    sign change has one root. Tangencies are retained at stationary boundaries.
    """
    grouped={}
    for rate,coefficient in zip(rates,coefficients):grouped[float(rate)]=grouped.get(float(rate),0.)+float(coefficient)
    terms=[(rate,c) for rate,c in sorted(grouped.items()) if c!=0]
    if len(terms)<2 or duration<=0:return []
    base=terms[0][0];scale=max(abs(c) for _,c in terms)
    rs=np.array([r-base for r,_ in terms]);cs=np.array([c/scale for _,c in terms])
    def value(t):return math.fsum(float(c)*math.exp(-float(r)*t) for r,c in zip(rs,cs))
    critical=exponential_roots(rs[1:],-rs[1:]*cs[1:],duration)
    limits=sorted({0.,duration,*critical});roots=[]
    for t in critical:
        # A flat extremum can touch zero without a sign change.
        local_scale=math.fsum(abs(float(c))*math.exp(-float(r)*t) for r,c in zip(rs,cs))
        if abs(value(t))<=1e-12*local_scale:roots.append(t)
    for a,b in zip(limits,limits[1:]):
        fa,fb=value(a),value(b)
        if fa==0 and 0<a<duration:roots.append(a)
        if fb==0 and 0<b<duration:roots.append(b)
        if fa==0 or fb==0 or (fa>0)==(fb>0):continue
        for _ in range(90):
            mid=(a+b)/2;fm=value(mid)
            if fm==0:a=b=mid;break
            if (fa>0)==(fm>0):a=mid;fa=fm
            else:b=mid
            if b-a<=1e-10*max(1.,abs(a),abs(b)):break
        roots.append((a+b)/2)
    return sorted(set(roots))


class ThermalSystem:
    """One constant-input phase, with passive symmetric conductances."""
    def __init__(self,nodes,links,phase):
        self.names=[n.name for n in nodes];self.capacity=np.array([n.capacity_j_per_k for n in nodes],dtype=float)
        self.sqrt=np.sqrt(self.capacity);self.phase=phase;size=len(nodes);indices={name:i for i,name in enumerate(self.names)}
        self.heat=np.array([phase.heat_w[name] for name in self.names],dtype=float)
        self.ambient_g=np.zeros(size);laplacian=np.zeros((size,size));adj=[set() for _ in nodes]
        for link in links:
            i=indices[link.first];g=phase.conductance_w_per_k[link.name]
            if link.second==AMBIENT:self.ambient_g[i]+=g;laplacian[i,i]+=g
            else:
                j=indices[link.second];laplacian[i,i]+=g;laplacian[j,j]+=g;laplacian[i,j]-=g;laplacian[j,i]-=g
                if g:adj[i].add(j);adj[j].add(i)
        self.laplacian=laplacian;self.force=self.heat+self.ambient_g*phase.ambient_c
        matrix=laplacian/self.sqrt[:,None]/self.sqrt[None,:]
        # Solve each connected component separately so isolated zero modes are known
        # from topology and are not guessed from a global eigenvalue threshold.
        self.rates=np.zeros(size);self.vectors=np.zeros((size,size));seen=set();column=0
        self.uncooled=[]
        for start in range(size):
            if start in seen:continue
            component={start};queue=[start];seen.add(start)
            while queue:
                for j in adj[queue.pop()]-seen:seen.add(j);component.add(j);queue.append(j)
            indices_component=sorted(component);block=matrix[np.ix_(indices_component,indices_component)]
            rates,vectors=np.linalg.eigh(block);uncooled=not any(self.ambient_g[i]>0 for i in component)
            if uncooled:
                rates[0]=0.;self.uncooled.append([self.names[i] for i in indices_component])
            positive=rates[1:] if uncooled else rates
            if len(positive) and (min(positive)<=0 or max(positive)/min(positive)>1e12):
                raise ValueError('Thermal time constants exceed the supported numerical conditioning; revise the network scales')
            if uncooled and len(rates)>1 and abs(float(np.linalg.eigvalsh(block)[0]))>1e-10*max(positive):
                raise ValueError('Insulated thermal mode failed its numerical check')
            width=len(component);self.rates[column:column+width]=rates
            self.vectors[np.ix_(indices_component,range(column,column+width))]=vectors;column+=width
        self.modal_force=self.vectors.T@(self.force/self.sqrt)
        duration=phase.duration_s;phi,_=_phi(self.rates,duration)
        self.transition=(self.vectors*np.exp(-self.rates*duration))@self.vectors.T
        self.transition=self.transition/self.sqrt[:,None]*self.sqrt[None,:]
        self.offset=(self.vectors@(self.modal_force*phi))/self.sqrt

    def trajectory(self,initial,time):
        initial=np.asarray(initial,dtype=float);modal=self.vectors.T@(self.sqrt*initial)
        change=self.modal_force-self.rates*modal;phi,_=_phi(self.rates,time)
        # Anchor exactly at entered initial values, reducing zero-time cancellation.
        return initial+(self.vectors@(change*phi))/self.sqrt

    def phase_result(self,initial,draw=True):
        initial=np.asarray(initial,dtype=float);duration=self.phase.duration_s
        modal=self.vectors.T@(self.sqrt*initial);change=self.modal_force-self.rates*modal
        coefficients=self.vectors*change/self.sqrt[:,None];times={0.,duration};extrema=[]
        for i,name in enumerate(self.names):
            roots=exponential_roots(self.rates,coefficients[i],duration)
            critical=[(t,float(self.trajectory(initial,t)[i])) for t in (0.,duration,*roots)]
            low=min(critical,key=lambda p:p[1]);high=max(critical,key=lambda p:p[1]);times.update(roots)
            extrema.append(dict(name=name,minimum_c=low[1],minimum_at_s=low[0],maximum_c=high[1],maximum_at_s=high[0],stationary_times_s=roots))
        if draw and duration:
            times.update(duration*i/40 for i in range(1,40))
            for rate in self.rates:
                if rate>0:times.update(t/rate for t in (.01,.1,.3,1,3,10,30) if 0<t/rate<duration)
        profile=[dict(time_s=t,temperature_c=dict(zip(self.names,map(float,self.trajectory(initial,t))))) for t in sorted(times)]
        final=self.trajectory(initial,duration);_,phi2=_phi(self.rates,duration)
        integral=initial*duration+(self.vectors@(change*phi2))/self.sqrt
        generated=float(math.fsum(self.heat)*duration)
        rejected=float(self.ambient_g@(integral-self.phase.ambient_c*duration))
        stored=float(self.capacity@(final-initial));residual=generated-rejected-stored
        if abs(residual)>1e-7*max(1.,abs(generated),abs(rejected),abs(stored)):
            raise ValueError('Thermal energy balance failed the numerical tolerance')
        return dict(name=self.phase.name,duration_s=duration,ambient_c=self.phase.ambient_c,
            start_temperature_c=dict(zip(self.names,map(float,initial))),end_temperature_c=dict(zip(self.names,map(float,final))),
            profile=profile,extrema=extrema,heat_generated_j=generated,heat_rejected_to_ambient_j=rejected,
            stored_energy_change_j=stored,energy_residual_j=residual,uncooled_components=self.uncooled)


def calculate_thermal_study(study):
    study.validate();source=calculate_study(study.source);names=[n.name for n in study.nodes]
    checks=[];systems=[];phases=[];initial=[n.initial_temperature_c for n in study.nodes]
    capacity_known=all(n.capacity_j_per_k is not None for n in study.nodes)
    known_initial=all(t is not None for t in initial);state=np.array(initial,dtype=float) if known_initial else None
    def check(name,passed,note):
        checks.append(dict(name=name,state='unassessed' if passed is None else 'within_limit' if passed else 'outside_limit',note=note))
    check('Heat capacity evidence',True if capacity_known and all(n.data_status=='declared' and n.source_reference.strip() and n.redistribution_basis.strip() for n in study.nodes) else None,
        'Each capacity and uniform-body approximation needs applicable evidence. Synthetic values are not physical measurements.')
    check('Sequence evidence',True if study.sequence_basis.strip() else None,'Thermal phases form an ordered timeline; aggregate lifetime duty is not automatically the real thermal cycle.')
    findings=[]
    for phase in study.phases:
        known=capacity_known and phase.ambient_c is not None and all(v is not None for v in [*phase.heat_w.values(),*phase.conductance_w_per_k.values()])
        check(phase.name+': losses and cooling evidence',True if known and phase.loss_basis.strip() and phase.cooling_basis.strip() else None,
            'Declared heat sources and linear conductances are independent inputs. Source efficiency is not substituted for a validated loss map.')
        system=None;row=None
        if known:
            try:
                system=ThermalSystem(study.nodes,study.links,phase)
                if state is not None:
                    row=system.phase_result(state);state=np.array(list(row['end_temperature_c'].values()))
            except (ValueError,np.linalg.LinAlgError) as exc:findings.append(f'{phase.name}: {exc}');system=None;state=None
        else:state=None
        systems.append(system)
        phases.append(row or dict(name=phase.name,duration_s=phase.duration_s,profile=[],extrema=[],unavailable_reason='Missing inputs, prior temperature history or unsupported numerical conditioning'))
    periodic=None;envelope=None
    if all(system is not None for system in systems):
        transition=np.eye(len(names));offset=np.zeros(len(names))
        for system in systems:offset=system.transition@offset+system.offset;transition=system.transition@transition
        closure=np.eye(len(names))-transition
        try:
            if np.linalg.cond(closure)>1e12:raise ValueError('No well-conditioned unique repeated-cycle equilibrium; an insulated component or extremely weak cooling may prevent convergence')
            # A tiny contraction is not resolved reliably by subtracting from I.
            if min(np.linalg.svd(closure,compute_uv=False))<1e-12:raise ValueError('Repeated-cycle cooling is below the numerical resolution of this phase duration')
            start=np.linalg.solve(closure,offset);state=start.copy();periodic_phases=[]
            for system in systems:
                row=system.phase_result(state);periodic_phases.append(row);state=np.array(list(row['end_temperature_c'].values()))
            residual=max(abs(state-start))
            if residual>1e-7*max(1.,max(abs(start))):raise ValueError('Repeated-cycle temperature closure failed')
            periodic=dict(start_temperature_c=dict(zip(names,map(float,start))),phases=periodic_phases,closure_residual_c=float(residual))
            if known_initial:
                difference=np.array(initial)-start;upper=max(0.,float(max(difference)));lower=min(0.,float(min(difference)))
                passive_floor=min([*initial,*(phase.ambient_c for phase in study.phases if phase.duration_s>0)])
                envelope=dict(upper_offset_c=upper,lower_offset_c=lower,nodes=[])
                for i,name in enumerate(names):
                    extrema=[row['extrema'][i] for row in periodic_phases]
                    envelope['nodes'].append(dict(name=name,minimum_bound_c=max(passive_floor,min(e['minimum_c'] for e in extrema)+lower),
                        maximum_bound_c=max(e['maximum_c'] for e in extrema)+upper))
        except (ValueError,np.linalg.LinAlgError) as exc:findings.append(str(exc))
    assessments=[]
    for i,node in enumerate(study.nodes):
        all_extrema=[r['extrema'][i] for r in phases if r['extrema']]
        if periodic:all_extrema.extend(r['extrema'][i] for r in periodic['phases'])
        low=min((e['minimum_c'] for e in all_extrema),default=None);high=max((e['maximum_c'] for e in all_extrema),default=None)
        complete=len([r for r in phases if r['extrema']])==len(phases)
        known_limits=node.minimum_allowable_c is not None and node.maximum_allowable_c is not None
        observed_ok=None if high is None or not known_limits else low>=node.minimum_allowable_c and high<=node.maximum_allowable_c
        bound=None if envelope is None else envelope['nodes'][i]
        bound_ok=None if bound is None or not known_limits else bound['minimum_bound_c']>=node.minimum_allowable_c and bound['maximum_bound_c']<=node.maximum_allowable_c
        model_known=node.model_minimum_c is not None and node.model_maximum_c is not None
        model_ok=None if high is None or not model_known else low>=node.model_minimum_c and high<=node.model_maximum_c
        model_bound_ok=None if bound is None or not model_known else bound['minimum_bound_c']>=node.model_minimum_c and bound['maximum_bound_c']<=node.model_maximum_c
        # Exceeding a conservative bound alone does not prove a physical crossing.
        status='outside_entered_limits' if observed_ok is False or model_ok is False else 'incomplete'
        if node.data_status=='synthetic':status='synthetic_'+status
        assessments.append(dict(name=node.name,assessment=status,calculated_minimum_c=low,calculated_maximum_c=high,
            entered_sequence_complete=complete,calculated_temperatures_within_allowable=observed_ok,
            calculated_temperatures_within_model_range=model_ok,all_repeated_cycles_bound=bound,
            all_repeated_cycles_bound_within_allowable=bound_ok,
            all_repeated_cycles_bound_within_model_range=model_bound_ok,
            bound_note='A bound crossing is unresolved, not a proved temperature exceedance. The maximum principle bounds every repeated cycle only for this passive, fixed-input model.'))
    check('Physical model coverage',None,'Spatial hot spots, nonlinear losses/radiation, flow, lubricant film, actual coefficients and thermal qualification are not established by this network.')
    inputs=asdict(study);digest=hashlib.sha256(json.dumps(inputs,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
    return dict(schema_version=1,app_version=__version__,method=METHOD,study_sha256=digest,source_study_sha256=source['study_sha256'],
        inputs=inputs,phases=phases,periodic_cycle=periodic,repeated_cycle_envelope=envelope,nodes=assessments,checks=checks,findings=findings,
        source_estimated_loss_power_w={r['name']:r['estimated_loss_power_w'] for r in source['duty_results']},
        production_approved=False,rated_output_torque_nm=None,rated_gearbox_life_hours=None,
        limitations=[
            'Each node is isothermal with constant positive heat capacity. Conductances and nonnegative heat inputs are constant within each ordered phase; actual losses and cooling must be established separately.',
            'The phase solution and energy integral use capacity-weighted symmetric modes. Continuous extrema are isolated from exponential sums; plotted samples do not determine maxima.',
            'Ambient is an infinite imposed-temperature bath. Conductances must include only effects justified as linear over the entered model range; nonlinear radiation and temperature-dependent losses are not solved.',
            'A repeated-cycle solution is a settled periodic state, not the first or worst warm-up cycle. A conservative maximum-principle envelope additionally bounds every repeated cycle from known initial temperatures.',
            'An exceeded conservative warm-up bound is unresolved, not proof of an actual limit crossing. Observed entered/periodic extrema are reported separately.',
            'Missing inputs or unknown previous temperatures prevent an entered-sequence result. A periodic calculation may still be available without an initial temperature. No cooling path can prevent a unique periodic equilibrium.',
            'Thermal phases are independent of aggregate lifetime duty; referenced gear cases supply context only. No loss is silently derived from assumed efficiency, rpm or torque.',
            'Declared temperature/model limits and provenance are not verified material data. No thermal capacity, lubricant adequacy, gearbox durability or production rating is approved.'])


def thermal_report_html(result):
    esc=lambda value:html.escape(str(value));fmt=lambda value:'Unassessed' if value is None else f'{value:.8g}'
    verdict=lambda value:'Unassessed' if value is None else 'Within entered range' if value else 'Outside entered range'
    rows=''.join(f"<tr><td>{esc(n['name'])}</td><td>{fmt(n['calculated_minimum_c'])}</td><td>{fmt(n['calculated_maximum_c'])}</td><td>{esc(n['assessment'].replace('_',' '))}</td></tr>" for n in result['nodes'])
    ranges=''
    for node in result['nodes']:
        entered=next(n for n in result['inputs']['nodes'] if n['name']==node['name'])
        ranges+=f"<tr><td>{esc(node['name'])}</td><td>{fmt(entered['minimum_allowable_c'])} to {fmt(entered['maximum_allowable_c'])}</td><td>{verdict(node['calculated_temperatures_within_allowable'])}</td><td>{fmt(entered['model_minimum_c'])} to {fmt(entered['model_maximum_c'])}</td><td>{verdict(node['calculated_temperatures_within_model_range'])}</td><td>{'Complete' if node['entered_sequence_complete'] else 'Incomplete'}</td></tr>"
    ranges=f'<h2>Temperature limits and model validity</h2><table><tr><th>Body</th><th>Allowable °C</th><th>Calculated temperatures</th><th>Model range °C</th><th>Calculated temperatures</th><th>Entered history</th></tr>{ranges}</table>'
    phases=''
    for label,sequence in [('Entered sequence',result['phases']),('Settled repeated cycle',[] if result['periodic_cycle'] is None else result['periodic_cycle']['phases'])]:
        phases+=f'<h2>{label}</h2>'
        if not sequence:phases+='<p>Unassessed: no unique supported periodic equilibrium.</p>'
        for row in sequence:
            phases+=f"<h3>{esc(row['name'])}</h3>"
            if not row['extrema']:phases+=f"<p>{esc(row['unavailable_reason'])}</p>";continue
            values=''.join(f"<tr><td>{esc(n['name'])}</td><td>{fmt(n['minimum_c'])}</td><td>{fmt(n['minimum_at_s'])}</td><td>{fmt(n['maximum_c'])}</td><td>{fmt(n['maximum_at_s'])}</td></tr>" for n in row['extrema'])
            phases+=f"<table><tr><th>Body</th><th>Minimum °C</th><th>Time s</th><th>Maximum °C</th><th>Time s</th></tr>{values}</table><p>Generated {fmt(row['heat_generated_j'])} J; rejected to ambient {fmt(row['heat_rejected_to_ambient_j'])} J; stored {fmt(row['stored_energy_change_j'])} J; energy residual {fmt(row['energy_residual_j'])} J.</p>"
    envelope='<p>All-cycle warm-up envelope unavailable.</p>'
    if result['repeated_cycle_envelope']:
        bound_verdict=lambda value:'Unassessed' if value is None else 'Within entered range' if value else 'Bound exceeds range; unresolved'
        values=''
        for node in result['nodes']:
            bound=node['all_repeated_cycles_bound']
            values+=f"<tr><td>{esc(node['name'])}</td><td>{fmt(bound['minimum_bound_c'])}</td><td>{fmt(bound['maximum_bound_c'])}</td><td>{bound_verdict(node['all_repeated_cycles_bound_within_allowable'])}</td><td>{bound_verdict(node['all_repeated_cycles_bound_within_model_range'])}</td></tr>"
        envelope=f'<table><tr><th>Body</th><th>Conservative minimum °C</th><th>Conservative maximum °C</th><th>Allowable range</th><th>Model range</th></tr>{values}</table><p>A bound exceeding an allowable is unresolved; it does not prove an actual crossing.</p>'
    checks=''.join(f"<li><strong>{esc(c['name'])}: {esc(c['state'].replace('_',' '))}.</strong> {esc(c['note'])}</li>" for c in result['checks'])
    findings=''.join(f'<li>{esc(f)}</li>' for f in result['findings']);limits=''.join(f'<li>{esc(l)}</li>' for l in result['limitations'])
    return ("<!doctype html><html><head><meta charset='utf-8'><title>Thermal study</title><style>body{font-family:Arial,sans-serif;margin:24px;max-width:1250px}table{border-collapse:collapse}td,th{border:1px solid #888;padding:6px}pre{white-space:pre-wrap}</style></head><body>"
        f"<h1>{esc(result['inputs']['name'])}</h1><p><strong>Declared thermal network — no production gearbox rating</strong></p><p>GearForge {esc(result['app_version'])}; method {esc(result['method'])}.</p><table><tr><th>Body</th><th>Calculated minimum °C</th><th>Calculated maximum °C</th><th>Assessment</th></tr>{rows}</table><ul>{findings}</ul>"
        +ranges+phases+f"<h2>Bound over all repeated cycles</h2>{envelope}<h2>Evidence and coverage</h2><ul>{checks}</ul><h2>Method limits</h2><ul>{limits}</ul><h2>Complete inputs</h2><pre>{esc(json.dumps(result['inputs'],indent=2,allow_nan=False))}</pre><p>Input fingerprint: {esc(result['study_sha256'])}</p></body></html>")


def export_thermal_study(study,destination):
    from .maintenance import write_manifest
    result=calculate_thermal_study(study);dest=Path(destination).absolute()
    if dest.exists() or dest.is_symlink():raise FileExistsError('Choose a new thermal assessment directory')
    dest.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.gearforge-thermal-',dir=dest.parent) as temporary:
        stage=Path(temporary)/'study';stage.mkdir();study.save(stage/'design.gearforge-thermal')
        atomic_text(stage/'calculation.json',json.dumps(result,indent=2,allow_nan=False));atomic_text(stage/'report.html',thermal_report_html(result))
        manifest=write_manifest(stage,kind='gearforge-thermal-study',method=METHOD,study_sha256=result['study_sha256'],production_approved=False)
        if dest.exists() or dest.is_symlink():raise FileExistsError('Thermal output directory already exists')
        stage.rename(dest)
    return dict(destination=str(dest),files=len(manifest['files'])+1,study_sha256=result['study_sha256'],production_approved=False)
