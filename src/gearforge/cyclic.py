"""Original finite-history cycle counting and bounded uniaxial fatigue arithmetic.

All samples refer to one fixed material point and signed normal direction.
No standard tables, empirical material data or reference implementation is bundled.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass, field
import csv
import hashlib
import html
import io
import json
import math
from pathlib import Path
import re
import tempfile

from . import __version__
from .engineering import EngineeringStudy, _integer, _model, _text
from .models import atomic_text, finite, read_text_limited, strict_json

METHOD = 'finite-uniaxial-history-1'
MAX_BYTES = 16_000_000
MAX_SAMPLES = 100_000
MAX_EXPANDED_SAMPLES = 10**15
EVIDENCE_STATES = ('unverified', 'synthetic', 'declared')


def optional_number(value, name, lower, upper):
    # Keep this mathematical history layer independent of shaft/NumPy imports.
    return None if value is None else finite(value, name, lower, upper)


class _CounterState:
    """Streaming turning points, four-point closures, then finite residual halves."""
    def __init__(self):
        self.stack = []
        self.last = None
        self.direction = 0

    def reversal(self, value, counts):
        self.stack.append(value)
        while len(self.stack) >= 4:
            a, b, c, d = self.stack[-4:]
            span = abs(c - b)
            if span > abs(b - a) or span > abs(d - c):
                break
            if span:
                counts[min(b, c), max(b, c)] += 2
            del self.stack[-3:-1]

    def sample(self, value, counts):
        if self.last is None:
            self.stack.append(value)
        elif value == self.last:
            return
        else:
            direction = 1 if value > self.last else -1
            if self.direction and direction != self.direction:
                self.reversal(self.last, counts)
            self.direction = direction
        self.last = value

    def signature(self):
        return tuple(self.stack), self.last, self.direction

    def finish(self, counts):
        if self.last is not None and self.last != self.stack[-1]:
            self.reversal(self.last, counts)
        residual = list(self.stack)
        for a, b in zip(residual, residual[1:]):
            if a != b:
                counts[min(a, b), max(a, b)] += 1
        return residual


def count_history(blocks):
    """Count ordered (stress samples, repetitions) without closing block seams.

    Closed repeated blocks accelerate only after the ENTIRE streaming state
    repeats. Cycles emitted between identical states can then be multiplied
    exactly; the residual stack is retained for the next block.
    """
    if not isinstance(blocks, list) or not 1 <= len(blocks) <= 200:
        raise ValueError('Enter 1..200 history blocks')
    prepared = []
    total = stored = 0
    previous = None
    for values, repetitions in blocks:
        _integer(repetitions, 'Block repetitions', 1, 10**12)
        if not isinstance(values, list) or not 2 <= len(values) <= MAX_SAMPLES:
            raise ValueError('Each counted block needs 2..100,000 stress samples')
        values = [finite(v, 'Local normal stress MPa', -100000, 100000) for v in values]
        if previous is not None and previous != values[0]:
            raise ValueError('Adjacent blocks must share their endpoint stress; supply an explicit transition')
        if repetitions > 1 and values[0] != values[-1]:
            raise ValueError('A repeated block must end at its starting stress')
        total += (len(values) - 1) * repetitions
        stored += len(values)
        previous = values[-1]
        prepared.append((values, repetitions))
    if stored > MAX_SAMPLES or total + 1 > MAX_EXPANDED_SAMPLES:
        raise ValueError('History exceeds 100,000 stored or 1e15 expanded samples')
    state = _CounterState()
    counts = Counter()
    metrics = []
    for values, repetitions in prepared:
        local = Counter()
        seen = {}
        done = processed = 0
        while done < repetitions:
            signature = state.signature()
            if signature in seen:
                earlier, earlier_counts = seen[signature]
                loops = (repetitions - done) // (done - earlier)
                if loops:
                    for key, value in list(local.items()):
                        local[key] += loops * (value - earlier_counts.get(key, 0))
                    done += loops * (done - earlier)
                    if done == repetitions:
                        break
            elif processed < 8:
                seen[signature] = done, local.copy()
            if processed >= 8:
                raise ValueError('Repeated history did not stabilize within eight passes; split the history')
            for value in values:
                state.sample(value, local)
            done += 1
            processed += 1
        counts.update(local)
        metrics.append(dict(repetitions=repetitions, processed_repetitions=processed,
                            skipped_repetitions=repetitions - processed,
                            processed_samples=processed * len(values)))
    residual = state.finish(counts)
    bins = [dict(minimum_stress_mpa=a, maximum_stress_mpa=b, range_mpa=b-a,
                 mean_mpa=(a+b)/2, half_cycles=n, count=n/2)
            for (a, b), n in sorted(counts.items()) if n]
    return dict(cycles=bins, residual_stresses_mpa=residual, blocks=metrics,
                expanded_samples=total + 1, stored_samples=stored,
                total_half_cycles=sum(counts.values()))


@dataclass
class StressSample:
    time_s: float = 0.
    stress_mpa: float = 0.

    def validate(self):
        self.time_s = finite(self.time_s, 'Sample time s', 0, 1e12)
        self.stress_mpa = finite(self.stress_mpa, 'Signed normal stress MPa', -100000, 100000)


def samples_sha256(samples):
    return hashlib.sha256(json.dumps([asdict(s) for s in samples], sort_keys=True,
                                    separators=(',', ':'), allow_nan=False).encode()).hexdigest()


@dataclass
class HistoryBlock:
    name: str = 'History block'
    duty_case_name: str = 'Continuous rated-input target'
    repetitions: int = 1
    samples: list[StressSample] = field(default_factory=list)
    starts_per_repeat: int | None = None
    data_status: str = 'unverified'
    source_reference: str = ''
    applicable_conditions: str = ''
    redistribution_basis: str = ''
    imported_file_sha256: str = ''
    imported_samples_sha256: str = ''

    def validate(self):
        for name in ('name', 'duty_case_name', 'source_reference', 'applicable_conditions', 'redistribution_basis'):
            _text(getattr(self, name), name, 120 if name in ('name', 'duty_case_name') else 4000,
                  name in ('name', 'duty_case_name'))
        _integer(self.repetitions, 'History repetitions', 1, 10**12)
        if self.starts_per_repeat is not None:
            _integer(self.starts_per_repeat, 'Starts per repeat', 0, 10**9)
        if self.data_status not in EVIDENCE_STATES:
            raise ValueError('Invalid history data status')
        if not isinstance(self.samples, list) or len(self.samples) == 1 or len(self.samples) > MAX_SAMPLES:
            raise ValueError('A block needs zero (unknown) or 2..100,000 samples')
        for sample in self.samples:
            if not isinstance(sample, StressSample):
                raise ValueError('Invalid stress sample')
            sample.validate()
        if self.samples:
            if self.samples[0].time_s != 0 or any(a.time_s >= b.time_s for a, b in zip(self.samples, self.samples[1:])):
                raise ValueError('Sample times must start at zero and strictly increase')
            if self.repetitions > 1 and self.samples[0].stress_mpa != self.samples[-1].stress_mpa:
                raise ValueError('A repeated block must end at its starting stress')
        for name in ('imported_file_sha256', 'imported_samples_sha256'):
            value = getattr(self, name)
            if not isinstance(value, str) or (value and not re.fullmatch('[0-9a-f]{64}', value)):
                raise ValueError('Invalid imported history fingerprint')
        if bool(self.imported_file_sha256) != bool(self.imported_samples_sha256):
            raise ValueError('Raw file and parsed sample fingerprints must be supplied together')


@dataclass
class SNPoint:
    failure_cycles: float = 1000.
    amplitude_mpa: float = 100.

    def validate(self):
        self.failure_cycles = finite(self.failure_cycles, 'Failure cycles', 1, 1e15)
        self.amplitude_mpa = finite(self.amplitude_mpa, 'Fully reversed stress amplitude MPa', .000001, 100000)


@dataclass
class HistoryMaterial:
    designation: str = ''
    data_status: str = 'unverified'
    source_reference: str = ''
    applicable_conditions: str = ''
    redistribution_basis: str = ''
    failure_definition: str = ''
    survival_probability: float | None = None
    confidence_probability: float | None = None
    elastic_limit_mpa: float | None = None
    ultimate_tensile_mpa: float | None = None
    minimum_temperature_c: float | None = None
    maximum_temperature_c: float | None = None
    sn_curve: list[SNPoint] = field(default_factory=list)

    def validate(self):
        for name in ('designation', 'source_reference', 'applicable_conditions', 'redistribution_basis', 'failure_definition'):
            _text(getattr(self, name), name, 4000)
        if self.data_status not in EVIDENCE_STATES:
            raise ValueError('Invalid fatigue material data status')
        for name, lo, hi in [('survival_probability', .000001, .999999), ('confidence_probability', .000001, .999999),
                            ('elastic_limit_mpa', .000001, 100000), ('ultimate_tensile_mpa', .000001, 100000),
                            ('minimum_temperature_c', -80, 200), ('maximum_temperature_c', -80, 200)]:
            setattr(self, name, optional_number(getattr(self, name), name, lo, hi))
        if self.minimum_temperature_c is not None and self.maximum_temperature_c is not None and self.minimum_temperature_c > self.maximum_temperature_c:
            raise ValueError('Material temperature range is reversed')
        if self.elastic_limit_mpa is not None and self.ultimate_tensile_mpa is not None and self.elastic_limit_mpa > self.ultimate_tensile_mpa:
            raise ValueError('Elastic stress limit cannot exceed ultimate tensile strength')
        if not isinstance(self.sn_curve, list) or len(self.sn_curve) == 1 or len(self.sn_curve) > 50:
            raise ValueError('Enter zero (unknown) or 2..50 S-N points')
        for point in self.sn_curve:
            if not isinstance(point, SNPoint):
                raise ValueError('Invalid S-N point')
            point.validate()
        if any(a.failure_cycles >= b.failure_cycles or a.amplitude_mpa <= b.amplitude_mpa
               for a, b in zip(self.sn_curve, self.sn_curve[1:])):
            raise ValueError('S-N failure cycles must increase and amplitudes must decrease')


@dataclass
class HistoryStudy:
    name: str = 'Local cyclic stress history'
    source: EngineeringStudy = field(default_factory=EngineeringStudy)
    point_definition: str = ''
    stress_state: str = 'unverified'
    history_basis: str = ''
    coverage_basis: str = ''
    history_minimum_temperature_c: float | None = None
    history_maximum_temperature_c: float | None = None
    stress_design_factor: float = 1.
    stress_factor_basis: str = ''
    mean_stress_model: str = 'unverified'
    mean_stress_basis: str = ''
    damage_limit: float | None = None
    damage_limit_basis: str = ''
    material: HistoryMaterial = field(default_factory=HistoryMaterial)
    blocks: list[HistoryBlock] = field(default_factory=lambda: [HistoryBlock()])
    notes: str = ''
    schema_version: int = 1

    def validate(self):
        _integer(self.schema_version, 'History schema', 1, 1)
        if not isinstance(self.source, EngineeringStudy) or not isinstance(self.material, HistoryMaterial):
            raise ValueError('Retained engineering study and history material are required')
        self.source.validate()
        self.material.validate()
        for name in ('name', 'point_definition', 'history_basis', 'coverage_basis', 'stress_factor_basis',
                     'mean_stress_basis', 'damage_limit_basis', 'notes'):
            _text(getattr(self, name), name, 10000 if name == 'notes' else 4000, name == 'name')
        if self.stress_state not in ('unverified', 'uniaxial_normal', 'other'):
            raise ValueError('Invalid stress state')
        if self.mean_stress_model not in ('unverified', 'fully_reversed_only', 'goodman_tension_only'):
            raise ValueError('Invalid mean stress model')
        for name in ('history_minimum_temperature_c', 'history_maximum_temperature_c'):
            setattr(self, name, optional_number(getattr(self, name), name, -80, 200))
        if self.history_minimum_temperature_c is not None and self.history_maximum_temperature_c is not None and self.history_minimum_temperature_c > self.history_maximum_temperature_c:
            raise ValueError('History temperature range is reversed')
        self.stress_design_factor = finite(self.stress_design_factor, 'Stress design factor', 1, 100)
        self.damage_limit = optional_number(self.damage_limit, 'Entered damage limit', .000001, 1)
        if not isinstance(self.blocks, list) or not 1 <= len(self.blocks) <= 200:
            raise ValueError('Enter 1..200 ordered history blocks')
        for block in self.blocks:
            if not isinstance(block, HistoryBlock):
                raise ValueError('Invalid history block')
            block.validate()
        if len({b.name for b in self.blocks}) != len(self.blocks):
            raise ValueError('History block names must be unique')
        if any(b.duty_case_name not in {d.name for d in self.source.duty} for b in self.blocks):
            raise ValueError('History blocks must refer to retained duty cases')
        if sum(len(b.samples) for b in self.blocks) > MAX_SAMPLES:
            raise ValueError('History exceeds 100,000 stored samples')
        if 1 + sum(max(0, len(b.samples)-1)*b.repetitions for b in self.blocks) > MAX_EXPANDED_SAMPLES:
            raise ValueError('History exceeds 1e15 expanded samples')
        for a, b in zip(self.blocks, self.blocks[1:]):
            if a.samples and b.samples and a.samples[-1].stress_mpa != b.samples[0].stress_mpa:
                raise ValueError('Adjacent blocks need equal endpoint stress; enter a transition block')

    @classmethod
    def from_dict(cls, data):
        if not isinstance(data, dict) or not isinstance(data.get('blocks'), list) or len(data['blocks']) > 200:
            raise ValueError('Invalid history study')
        data = dict(data)
        data['source'] = EngineeringStudy.from_dict(data.get('source'))
        material = data.get('material')
        if not isinstance(material, dict) or not isinstance(material.get('sn_curve'), list) or len(material['sn_curve']) > 50:
            raise ValueError('Invalid history material')
        material = dict(material)
        material['sn_curve'] = [_model(SNPoint, p) for p in material['sn_curve']]
        data['material'] = _model(HistoryMaterial, material)
        blocks = []
        sample_total = 0
        for block in data['blocks']:
            if not isinstance(block, dict) or not isinstance(block.get('samples'), list) or len(block['samples']) > MAX_SAMPLES:
                raise ValueError('Invalid history samples')
            sample_total += len(block['samples'])
            if sample_total > MAX_SAMPLES:
                raise ValueError('History exceeds 100,000 stored samples')
            block = dict(block)
            block['samples'] = [_model(StressSample, s) for s in block['samples']]
            blocks.append(_model(HistoryBlock, block))
        data['blocks'] = blocks
        study = _model(cls, data)
        study.validate()
        return study

    @classmethod
    def load(cls, path):
        return cls.from_dict(strict_json(read_text_limited(Path(path), MAX_BYTES, 'Stress history study')))

    def save(self, path):
        self.validate()
        content = json.dumps(asdict(self), indent=2, allow_nan=False)
        if len(content.encode('utf-8')) > MAX_BYTES:
            raise ValueError('History study exceeds 16 MB')
        atomic_text(Path(path), content)


def history_from_study(source):
    source = EngineeringStudy.from_dict(asdict(source))
    return HistoryStudy(source=source, blocks=[HistoryBlock(name=d.name, duty_case_name=d.name) for d in source.duty])


def parse_sample_csv(content):
    if not isinstance(content, str) or len(content.encode('utf-8')) > MAX_BYTES:
        raise ValueError('Sample CSV exceeds 16 MB')
    rows = csv.reader(io.StringIO(content.lstrip('\ufeff')), strict=True)
    samples = []
    try:
        if next(rows, None) != ['time_s', 'stress_mpa']:
            raise ValueError('CSV header must be time_s,stress_mpa')
        for row in rows:
            if len(row) != 2 or len(samples) >= MAX_SAMPLES:
                raise ValueError('CSV needs two columns and at most 100,000 samples')
            sample = StressSample(float(row[0]), float(row[1]))
            sample.validate()
            samples.append(sample)
    except (csv.Error, OverflowError) as exc:
        raise ValueError('Invalid stress history CSV') from exc
    block = HistoryBlock(samples=samples)
    block.validate()
    if not samples:
        raise ValueError('CSV needs at least two samples')
    return samples


def import_sample_csv(path, block):
    path = Path(path)
    if path.stat().st_size > MAX_BYTES:
        raise ValueError('Sample CSV exceeds 16 MB')
    with path.open('rb') as stream:
        raw = stream.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise ValueError('Sample CSV exceeds 16 MB')
    try:
        samples = parse_sample_csv(raw.decode('utf-8-sig'))
    except UnicodeDecodeError as exc:
        raise ValueError('Sample CSV must be UTF-8') from exc
    # Validate a fresh copy before touching the caller's block.
    candidate = HistoryBlock(**{**block.__dict__, 'samples': samples,
        'imported_file_sha256': hashlib.sha256(raw).hexdigest(), 'imported_samples_sha256': samples_sha256(samples)})
    candidate.validate()
    block.__dict__.update(candidate.__dict__)


def sn_failure_cycles(curve, amplitude):
    if not curve or not curve[-1].amplitude_mpa <= amplitude <= curve[0].amplitude_mpa:
        return None
    for point in curve:
        if amplitude == point.amplitude_mpa:
            return point.failure_cycles
    for a, b in zip(curve, curve[1:]):
        if b.amplitude_mpa < amplitude < a.amplitude_mpa:
            fraction = math.log(amplitude/a.amplitude_mpa) / math.log(b.amplitude_mpa/a.amplitude_mpa)
            return math.exp(math.log(a.failure_cycles) + fraction * math.log(b.failure_cycles/a.failure_cycles))
    return None


def calculate_history_study(study):
    study.validate()
    inputs = asdict(study)
    digest = hashlib.sha256(json.dumps(inputs, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()
    result = dict(method=METHOD, application_version=__version__, study_sha256=digest, inputs=inputs,
        calculation_available=False, fatigue_damage_available=False, damage=None, known_damage_lower_bound=None,
        entered_limit_assessment='unavailable', declared_input_evidence_complete=False,
        production_approved=False, rated_output_torque_nm=None, rated_gearbox_life_hours=None,
        coverage=[], coverage_complete=False, cycles=[], counting=None, findings=[], block_provenance=[])
    findings = result['findings']
    for duty in study.source.duty:
        blocks = [b for b in study.blocks if b.duty_case_name == duty.name]
        duration = math.fsum(b.samples[-1].time_s*b.repetitions for b in blocks if b.samples)
        known = bool(blocks) and all(b.samples for b in blocks)
        starts_known = bool(blocks) and all(b.starts_per_repeat is not None for b in blocks)
        starts = sum(b.starts_per_repeat*b.repetitions for b in blocks) if starts_known else None
        matched = known and math.isclose(duration, duty.duration_hours*3600, rel_tol=1e-9, abs_tol=1e-6)
        result['coverage'].append(dict(name=duty.name, expected_seconds=duty.duration_hours*3600,
            entered_seconds=duration if known else None, duration_matched=matched,
            expected_starts=duty.starts, entered_starts=starts, starts_matched=starts == duty.starts))
    result['coverage_complete'] = all(c['duration_matched'] and c['starts_matched'] for c in result['coverage'])
    if not result['coverage_complete']:
        findings.append('History duration or start counts do not cover every retained duty case.')
    for block in study.blocks:
        fingerprint = samples_sha256(block.samples)
        result['block_provenance'].append(dict(name=block.name, samples_sha256=fingerprint,
            imported_file_sha256=block.imported_file_sha256,
            imported_samples_unchanged=fingerprint == block.imported_samples_sha256 if block.imported_samples_sha256 else None))
        if block.imported_samples_sha256 and fingerprint != block.imported_samples_sha256:
            findings.append(f'Block {block.name}: current samples differ from the imported CSV fingerprint; review the edited history basis.')
    if any(not b.samples for b in study.blocks):
        findings.append('At least one history block has no samples; the concatenated history is unavailable.')
        return result
    counting = count_history([([s.stress_mpa for s in b.samples], b.repetitions) for b in study.blocks])
    result.update(calculation_available=True, counting={k: v for k, v in counting.items() if k != 'cycles'})
    material = study.material
    low = min(s.stress_mpa for b in study.blocks for s in b.samples)*study.stress_design_factor
    high = max(s.stress_mpa for b in study.blocks for s in b.samples)*study.stress_design_factor
    elastic_ok = material.elastic_limit_mpa is not None and max(abs(low), abs(high)) <= material.elastic_limit_mpa
    result.update(design_minimum_stress_mpa=low, design_maximum_stress_mpa=high,
                  within_entered_elastic_limit=elastic_ok if material.elastic_limit_mpa is not None else None)
    temperature_ok = (study.history_minimum_temperature_c is not None and study.history_maximum_temperature_c is not None
        and material.minimum_temperature_c is not None and material.maximum_temperature_c is not None
        and material.minimum_temperature_c <= study.history_minimum_temperature_c <= study.history_maximum_temperature_c <= material.maximum_temperature_c)
    common = []
    if study.stress_state != 'uniaxial_normal':
        common.append('A declared uniaxial local elastic normal stress state is required for fatigue arithmetic.')
    if not elastic_ok:
        common.append('The complete factored stress history is outside, or lacks, the entered elastic limit.')
    if not temperature_ok:
        common.append('The history temperature range is outside, or lacks, the material temperature range.')
    if not material.sn_curve:
        common.append('The fully reversed failure S-N curve is missing.')
    elif material.elastic_limit_mpa is not None and material.sn_curve[0].amplitude_mpa > material.elastic_limit_mpa:
        common.append('The entered S-N curve includes amplitudes above the local elastic limit; provide an entirely elastic applicable curve.')
    if study.mean_stress_model == 'unverified':
        common.append('A supported mean stress model must be selected.')
    if study.mean_stress_model == 'goodman_tension_only' and material.ultimate_tensile_mpa is None:
        common.append('The selected mean stress correction requires ultimate tensile strength.')
    findings.extend(common)
    for cycle in counting['cycles']:
        amplitude = cycle['range_mpa']*study.stress_design_factor/2
        mean = cycle['mean_mpa']*study.stress_design_factor
        equivalent = None
        reason = '; '.join(common)
        if not common:
            if study.mean_stress_model == 'fully_reversed_only' and abs(mean) > 1e-12*max(1, amplitude):
                reason = 'Nonzero cycle mean is unsupported by the fully reversed model.'
            elif study.mean_stress_model == 'goodman_tension_only' and mean >= material.ultimate_tensile_mpa:
                reason = 'Tensile cycle mean reaches the entered ultimate strength.'
            else:
                equivalent = amplitude if study.mean_stress_model == 'fully_reversed_only' else amplitude/(1-max(0, mean)/material.ultimate_tensile_mpa)
        life = sn_failure_cycles(material.sn_curve, equivalent) if equivalent is not None else None
        if equivalent is not None and life is None:
            reason = 'Equivalent amplitude is outside the entered S-N endpoints; no extrapolation.'
        result['cycles'].append({**cycle, 'design_amplitude_mpa': amplitude, 'design_mean_mpa': mean,
            'equivalent_fully_reversed_amplitude_mpa': equivalent, 'failure_cycles': life,
            'damage': cycle['count']/life if life is not None else None, 'unavailable_reason': reason})
    available = not common and all(c['damage'] is not None for c in result['cycles'])
    lower = math.fsum(c['damage'] for c in result['cycles'] if c['damage'] is not None) if not common else None
    result.update(fatigue_damage_available=available, damage=lower if available else None, known_damage_lower_bound=lower)
    if not common and not available:
        findings.append('Some counted cycles have unsupported mean stress or S-N amplitude; total damage is unavailable.')
    if study.damage_limit is not None and lower is not None:
        if lower > study.damage_limit:
            result['entered_limit_assessment'] = 'exceeds_entered_limit' if available else 'known_lower_bound_exceeds_entered_limit'
        elif available:
            result['entered_limit_assessment'] = 'within_entered_limit_for_entered_history'
    evidence = (available and result['coverage_complete'] and material.data_status == 'declared'
        and all(getattr(material, key).strip() for key in ('designation', 'source_reference', 'applicable_conditions', 'redistribution_basis', 'failure_definition'))
        and material.survival_probability is not None and material.confidence_probability is not None
        and study.damage_limit is not None
        and all(getattr(study, key).strip() for key in ('point_definition', 'history_basis', 'coverage_basis', 'stress_factor_basis', 'mean_stress_basis', 'damage_limit_basis'))
        and all(b.data_status == 'declared' and b.source_reference.strip() and b.applicable_conditions.strip() and b.redistribution_basis.strip() for b in study.blocks)
        and all(b['imported_samples_unchanged'] is not False for b in result['block_provenance']))
    result['declared_input_evidence_complete'] = bool(evidence)
    findings.append('Cycle counting retains block transitions and finite residual half cycles. Miner damage does not model load-sequence, plasticity, multiaxial or thermomechanical effects.')
    findings.append('These results describe the entered history at one material point; they do not establish tooth-root, gear or gearbox load/life ratings.')
    return result


def synthetic_history_example():
    study = HistoryStudy(name='Synthetic local stress history — arithmetic only', stress_state='uniaxial_normal',
        point_definition='One invented material point, signed local normal direction. Not a solved or measured gear history.',
        history_basis='Original synthetic waveform, no material or component qualification.',
        coverage_basis='Invented 40 ms closed block repeated 900,000,000 times gives 10,000 hours; zero starts.',
        history_minimum_temperature_c=40., history_maximum_temperature_c=40.,
        stress_factor_basis='Synthetic unit stress factor.', mean_stress_model='goodman_tension_only',
        mean_stress_basis='Illustrative tensile-only Goodman correction, with no beneficial compressive mean credit.',
        damage_limit=.5, damage_limit_basis='Invented arithmetic comparison threshold.')
    study.material = HistoryMaterial(designation='Synthetic material — not an allowable', data_status='synthetic',
        source_reference='Original GearForge arithmetic fixture.', applicable_conditions='Invented fully reversed elastic amplitude data.',
        redistribution_basis='Original GearForge fixture, Apache-2.0.', failure_definition='Invented crack-initiation endpoint.',
        survival_probability=.99, confidence_probability=.95, elastic_limit_mpa=250., ultimate_tensile_mpa=600.,
        minimum_temperature_c=20., maximum_temperature_c=80.,
        sn_curve=[SNPoint(1e3,220.), SNPoint(1e9,120.), SNPoint(1e14,10.)])
    study.blocks = [HistoryBlock(name='Invented repeated waveform', repetitions=900_000_000,
        samples=[StressSample(t, s) for t, s in zip([0,.01,.015,.02,.025,.03,.04], [0,100,20,80,0,-60,0])],
        starts_per_repeat=0, data_status='synthetic', source_reference='Original GearForge waveform.',
        applicable_conditions='One synthetic point and normal stress direction at 40 degrees C.',
        redistribution_basis='Original GearForge fixture, Apache-2.0.')]
    study.validate()
    return study


def history_report_html(result):
    esc = lambda v: html.escape(str(v))
    rows = ''.join('<tr>' + ''.join(f'<td>{esc(c.get(k))}</td>' for k in
        ('minimum_stress_mpa', 'maximum_stress_mpa', 'count', 'equivalent_fully_reversed_amplitude_mpa', 'failure_cycles', 'damage', 'unavailable_reason')) + '</tr>'
        for c in result['cycles'][:200])
    metadata = {k: v for k, v in result.items() if k not in ('cycles', 'inputs')}
    if result['counting'] is not None:
        metadata['counting'] = {**result['counting'], 'residual_stresses_mpa': result['counting']['residual_stresses_mpa'][:200],
            'residual_samples_shown': min(200, len(result['counting']['residual_stresses_mpa'])),
            'residual_samples_total': len(result['counting']['residual_stresses_mpa'])}
    # Large waveforms remain in the editable input and CSV, not a million-cell HTML report.
    basis = {k: v for k, v in result['inputs'].items() if k != 'blocks'}
    basis['blocks'] = [{k: v for k, v in b.items() if k != 'samples'} | {'sample_count': len(b['samples'])} for b in result['inputs']['blocks']]
    return ('<!doctype html><html><head><meta charset="utf-8"><title>Local stress history</title>'
        '<style>body{font:15px sans-serif;margin:28px;color:#172033}table{border-collapse:collapse}td,th{border:1px solid #bbb;padding:6px}pre{white-space:pre-wrap;overflow-wrap:anywhere}</style></head><body>'
        f'<h1>{esc(result["inputs"]["name"])}</h1><p>Production approval: false. No rated gearbox torque or life.</p>'
        f'<p>Entered-history damage: {esc(result["damage"])}. Assessment: {esc(result["entered_limit_assessment"])}</p>'
        '<h2>Counted cycles</h2><p>First 200 bins shown; all bins and template samples are retained in JSON/CSV. Stress units: MPa. Counts include finite half cycles.</p>'
        '<table><tr><th>Min</th><th>Max</th><th>Count</th><th>Equivalent amplitude</th><th>Failure cycles</th><th>Damage</th><th>Unavailable reason</th></tr>'
        f'{rows}</table><h2>Assessment and provenance</h2><pre>{esc(json.dumps(metadata, indent=2, allow_nan=False))}</pre>'
        f'<h2>Entered basis</h2><pre>{esc(json.dumps(basis, indent=2, allow_nan=False))}</pre></body></html>')


def history_csv_files(result):
    def write(header, rows):
        out = io.StringIO(newline='')
        writer = csv.writer(out)
        writer.writerow(header)
        for row in rows:
            writer.writerow([("'"+v if isinstance(v, str) and v.lstrip().startswith(('=', '+', '-', '@')) else v) for v in row])
        return out.getvalue()
    keys = ['minimum_stress_mpa', 'maximum_stress_mpa', 'range_mpa', 'mean_mpa', 'half_cycles', 'count',
            'design_amplitude_mpa', 'design_mean_mpa', 'equivalent_fully_reversed_amplitude_mpa', 'failure_cycles', 'damage', 'unavailable_reason']
    return {'cycles.csv': write(keys, ([c[k] for k in keys] for c in result['cycles'])),
        'history-samples.csv': write(['block_index', 'block_name', 'duty_case_name', 'repetitions', 'time_s', 'stress_mpa'],
            ([i, b['name'], b['duty_case_name'], b['repetitions'], s['time_s'], s['stress_mpa']]
             for i, b in enumerate(result['inputs']['blocks']) for s in b['samples']))}


def export_history_study(study, destination):
    from .maintenance import write_manifest
    dest = Path(destination).absolute()
    if dest.exists() or dest.is_symlink():
        raise ValueError('Export destination already exists; choose a new directory')
    dest.parent.mkdir(parents=True, exist_ok=True)
    result = calculate_history_study(study)
    with tempfile.TemporaryDirectory(prefix='.gearforge-history-', dir=dest.parent) as temp:
        stage = Path(temp)/'package'
        stage.mkdir()
        study.save(stage/'inputs.gearforge-history')
        atomic_text(stage/'calculation.json', json.dumps(result, indent=2, allow_nan=False))
        atomic_text(stage/'report.html', history_report_html(result))
        for name, content in history_csv_files(result).items():
            atomic_text(stage/name, content)
        manifest = write_manifest(stage, kind='gearforge-stress-history', method=METHOD,
                                  study_sha256=result['study_sha256'], production_approved=False)
        if dest.exists() or dest.is_symlink():
            raise FileExistsError('History export destination already exists')
        stage.rename(dest)
    return dict(destination=str(dest), files=len(manifest['files'])+1, study_sha256=result['study_sha256'],
                calculation_available=result['calculation_available'], fatigue_damage_available=result['fatigue_damage_available'],
                damage=result['damage'], production_approved=False)
