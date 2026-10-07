"""Original fixtures, separate MIT rainflow reference, and 60-digit fatigue math."""
from collections import Counter
from decimal import Decimal, localcontext
import argparse
import json
import math
from pathlib import Path
import random
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def fixtures():
    cases = [dict(name='monotonic finite half', blocks=[([0, 100], 1)]),
             dict(name='plateau', blocks=[([10, 10, 10], 20)]),
             dict(name='boundary closures', blocks=[([0, 50, -10, 0], 5), ([0, 100, -80, 0], 3), ([0, 50, -10, 0], 5)]),
             dict(name='nested unequal means', blocks=[([0, 100, 20, 80, 0, -60, 0], 29)])]
    rng = random.Random(6031)
    for index in range(400):
        blocks = []
        last = rng.randint(-10, 10)
        for _ in range(rng.randint(1, 6)):
            values = [last] + [rng.randint(-20, 20) for _ in range(rng.randint(0, 25))]
            repetitions = rng.randint(1, 20)
            values.append(values[0] if repetitions > 1 else rng.randint(-20, 20))
            last = values[-1]
            blocks.append((values, repetitions))
        cases.append(dict(name=f'Original random history {index}', blocks=blocks))
    for index in range(10):
        values = [math.sin(t*.093)*(1+.3*math.cos(t*.017)) + index*.1 for t in range(300)]
        values[-1] = values[0]
        cases.append(dict(name=f'Original smooth history {index}', blocks=[(values, 3)]))
    return cases


def reference(cases):
    # This process does not import GearForge or use its cycle-counting algorithm.
    import importlib.metadata
    import rainflow
    if importlib.metadata.version('rainflow') != '3.2.0':
        raise ValueError('Install pinned rainflow==3.2.0 in the reference environment')
    results = []
    for case in cases:
        signal = [v for values, repetitions in case['blocks'] for _ in range(repetitions) for v in values]
        # The reference ignores a two-sample input. A terminal plateau preserves
        # the physical path and gives its API enough samples to retain the endpoint.
        if len(signal) == 2:
            signal.append(signal[-1])
        counts = Counter()
        for span, mean, count, i, j in rainflow.extract_cycles(signal):
            if span:
                counts[tuple(sorted((signal[i], signal[j])))] += int(2*count)
        results.append([dict(minimum_stress_mpa=a, maximum_stress_mpa=b, half_cycles=n)
                        for (a, b), n in sorted(counts.items())])
    return results


def fatigue_reference(study, cycles):
    with localcontext() as context:
        context.prec = 60
        D = lambda value: Decimal(str(value))
        material = study.material
        output = []
        for cycle in cycles:
            factor = D(study.stress_design_factor)
            a, b = D(cycle['minimum_stress_mpa'])*factor, D(cycle['maximum_stress_mpa'])*factor
            amplitude = (b-a)/2
            mean = (a+b)/2
            equivalent = amplitude/(1-max(mean, D(0))/D(material.ultimate_tensile_mpa))
            life = None
            for lo, hi in zip(material.sn_curve, material.sn_curve[1:]):
                if D(hi.amplitude_mpa) <= equivalent <= D(lo.amplitude_mpa):
                    log_life = D(lo.failure_cycles).ln() + (equivalent.ln()-D(lo.amplitude_mpa).ln()) * (D(hi.failure_cycles).ln()-D(lo.failure_cycles).ln()) / (D(hi.amplitude_mpa).ln()-D(lo.amplitude_mpa).ln())
                    life = log_life.exp()
                    break
            output.append(dict(equivalent_fully_reversed_amplitude_mpa=float(equivalent),
                failure_cycles=float(life) if life is not None else None,
                damage=float(D(cycle['half_cycles'])/2/life) if life is not None else None))
        return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reference-python', default=sys.executable)
    parser.add_argument('--reference-process', action='store_true')
    parser.add_argument('--out', type=Path, default=ROOT/'build/history-reference-comparison.json')
    parser.add_argument('--write-fixture', type=Path)
    args = parser.parse_args()
    if args.reference_process:
        print(json.dumps(reference(json.load(sys.stdin)), allow_nan=False))
        return 0
    cases = fixtures()
    child = subprocess.run([args.reference_python, str(Path(__file__).resolve()), '--reference-process'],
        input=json.dumps(cases), capture_output=True, text=True, check=True, timeout=60)
    expected = json.loads(child.stdout)
    sys.path.insert(0, str(ROOT/'src'))
    from gearforge.cyclic import count_history, synthetic_history_example, calculate_history_study
    from gearforge.models import atomic_text
    failures = []
    comparisons = 0
    for case, wanted in zip(cases, expected, strict=True):
        result = count_history([(list(v), n) for v, n in case['blocks']])
        actual = [{k: c[k] for k in ('minimum_stress_mpa', 'maximum_stress_mpa', 'half_cycles')} for c in result['cycles']]
        comparisons += 1 + 3*len(wanted)
        if actual != wanted:
            failures.append(dict(name=case['name'], actual=actual, expected=wanted))
        case['expected_cycles'] = wanted
    arithmetic = []
    maximum_relative_error = 0.
    for factor in (1., 1.2, 2.):
        study = synthetic_history_example()
        study.stress_design_factor = factor
        actual = calculate_history_study(study)
        expected_math = fatigue_reference(study, actual['cycles'])
        for row, wanted in zip(actual['cycles'], expected_math, strict=True):
            for field, value in wanted.items():
                comparisons += 1
                if value is None:
                    passed = row[field] is None
                else:
                    passed = row[field] is not None and math.isclose(row[field], value, rel_tol=1e-11, abs_tol=1e-14)
                    if row[field] is not None and value:
                        maximum_relative_error = max(maximum_relative_error, abs((row[field]-value)/value))
                if not passed:
                    failures.append(dict(factor=factor, field=field, actual=row[field], expected=value))
        expected_damage = math.fsum(row['damage'] for row in expected_math) if all(row['damage'] is not None for row in expected_math) else None
        comparisons += 1
        if not math.isclose(actual['damage'], expected_damage, rel_tol=1e-11, abs_tol=1e-14):
            failures.append(dict(factor=factor, actual=actual['damage'], expected=expected_damage))
        arithmetic.append(dict(stress_design_factor=factor, expected_cycles=expected_math, expected_damage=expected_damage))
    report = dict(reference='https://github.com/iamlikeme/rainflow', reference_version='3.2.0',
        license='MIT, Copyright (c) 2018 Piotr Janiszewski; separately installed, not bundled',
        provenance='Original Apache-2.0 fixtures and adapter. Reference public API, independent Decimal arithmetic; no restricted standards or material data.',
        scope='Exact cycle extrema/half counts on finite concatenated histories; repeat acceleration compared with fully expanded signals; bounded Goodman/S-N/Miner arithmetic. No ASTM compliance or physical fatigue qualification.',
        two_sample_adapter='Append an identical final endpoint; reference API otherwise omits two-sample histories. Zero-range reference cycles are discarded.',
        comparisons=comparisons, maximum_relative_error=maximum_relative_error, passed=not failures, failures=failures,
        cases=cases, arithmetic=arithmetic)
    content = json.dumps(report, indent=2, allow_nan=False)
    atomic_text(args.out, content)
    if args.write_fixture:
        if failures:
            raise SystemExit('Comparison failed; fixture not written')
        atomic_text(args.write_fixture, content)
    print(json.dumps({k: report[k] for k in ('comparisons', 'maximum_relative_error', 'passed', 'failures')}))
    return int(bool(failures))


if __name__ == '__main__':
    raise SystemExit(main())
