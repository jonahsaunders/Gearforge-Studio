"""Compare GearForge against a separately checked-out GPL-3.0 FreeCAD Gears.

No reference implementation is copied, installed or bundled with GearForge.
The separate process returns scalar geometry results for our own test inputs.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from gearforge.engineering import GearPair, pair_geometry
from gearforge.models import atomic_text

REFERENCE_COMMIT = "83ec154b1925347622b61812f75d2ed51e956b9f"
CASES = [
    dict(name="agreed-steel-spur-target", pair=dict(normal_module_mm=2, pinion_teeth=20, wheel_teeth=100)),
    dict(name="spur-shift-positive", pair=dict(normal_module_mm=1.5, pinion_teeth=24, wheel_teeth=72, pinion_profile_shift=.3, wheel_profile_shift=.1)),
    dict(name="spur-shift-balanced", pair=dict(normal_module_mm=3, pinion_teeth=30, wheel_teeth=60, pinion_profile_shift=.2, wheel_profile_shift=-.2)),
    dict(name="helical-right-30", pair=dict(normal_module_mm=2, pinion_teeth=24, wheel_teeth=72, pinion_helix_angle_deg=30)),
    dict(name="helical-left-shifted", pair=dict(normal_module_mm=2.5, pinion_teeth=28, wheel_teeth=84, pinion_helix_angle_deg=-20, pinion_profile_shift=.2, wheel_profile_shift=.15)),
    dict(name="helical-pressure-25", pair=dict(normal_module_mm=1, pinion_teeth=40, wheel_teeth=80, normal_pressure_angle_deg=25, pinion_helix_angle_deg=15, pinion_profile_shift=-.1, wheel_profile_shift=.3)),
]

# Adapter uses the reference's public constructors/functions, not its source.
ADAPTER = r'''
import json, math, sys
sys.path.insert(0, sys.argv[1])
from pygears.involute_tooth import InvoluteTooth
from pygears.computation import compute_shifted_gears
results = []
for case in json.load(sys.stdin):
    p = case['pair']; beta = math.radians(p['pinion_helix_angle_deg'])
    def gear(teeth, shift, head=0):
        return InvoluteTooth(m=p['normal_module_mm'], num_teeth=teeth,
            pressure_angle=math.radians(p['normal_pressure_angle_deg']),
            beta=beta, shift=shift, head=head, clearance=.25, properties_from_tool=True)
    first = gear(p['pinion_teeth'], p['pinion_profile_shift'])
    distance, angle = compute_shifted_gears(first.m, first.pressure_angle_t,
        p['pinion_teeth'], p['wheel_teeth'],
        p['pinion_profile_shift']*math.cos(beta), p['wheel_profile_shift']*math.cos(beta))
    reference_distance = first.m*(p['pinion_teeth']+p['wheel_teeth'])/2
    shortening = p['pinion_profile_shift']+p['wheel_profile_shift']-(distance-reference_distance)/p['normal_module_mm']
    expected = dict(transverse_module_mm=float(first.m),
        transverse_pressure_angle_deg=math.degrees(first.pressure_angle_t),
        operating_center_distance_mm=float(distance), operating_pressure_angle_deg=math.degrees(angle))
    for name, teeth, shift in [('pinion',p['pinion_teeth'],p['pinion_profile_shift']),
                                ('wheel',p['wheel_teeth'],p['wheel_profile_shift'])]:
        obj = gear(teeth, shift, head=-shortening)
        for key, attribute in [('reference_diameter_mm','d'),('base_diameter_mm','dg'),
                               ('tip_diameter_mm','da'),('root_diameter_mm','df')]:
            expected[name+'.'+key] = float(getattr(obj,attribute))
    results.append(dict(name=case['name'], pair=p, expected=expected))
print(json.dumps(results,allow_nan=False))
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference-checkout", type=Path, required=True)
    parser.add_argument("--out", type=Path, default=ROOT / "build/open-reference-comparison.json")
    parser.add_argument("--write-fixture", type=Path)
    args = parser.parse_args()
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=args.reference_checkout, text=True).strip()
    if commit != REFERENCE_COMMIT:
        raise SystemExit("Reference checkout does not match the recorded commit")
    if subprocess.check_output(["git", "status", "--porcelain", "--untracked-files=no"], cwd=args.reference_checkout, text=True).strip():
        raise SystemExit("Reference checkout has tracked modifications")
    from dataclasses import asdict
    cases = [dict(name=c["name"], pair=asdict(GearPair(**c["pair"]))) for c in CASES]
    process = subprocess.run([sys.executable, "-c", ADAPTER, str(args.reference_checkout.resolve())],
                             input=json.dumps(cases), capture_output=True, text=True, timeout=60, check=True)
    reference = json.loads(process.stdout)
    failures = []
    maximum_absolute_error = 0
    for case in reference:
        actual = pair_geometry(GearPair(**case["pair"]))
        for key, expected in case["expected"].items():
            value = actual
            for part in key.split("."):value = value[part]
            maximum_absolute_error = max(maximum_absolute_error, abs(value - expected))
            if not math.isclose(value, expected, rel_tol=2e-7, abs_tol=1e-7):
                failures.append(dict(case=case["name"], field=key, actual=value, expected=expected))
    report = dict(reference="https://github.com/looooo/freecad.gears", reference_license="GPL-3.0-or-later",
                  reference_commit=commit, reference_runtime="Separate comparison process; not an application dependency",
                  fixture_origin="Numerical outputs for GearForge-authored inputs; no upstream source, figures or document text copied",
                  scope="External gear reference/base/tip/root diameters, pressure angles and operating center distance only",
                  tolerance=dict(relative=2e-7, absolute=1e-7), cases=reference,
                  comparisons=sum(len(c["expected"]) for c in reference),
                  maximum_absolute_error=maximum_absolute_error, failures=failures, passed=not failures)
    atomic_text(args.out, json.dumps(report, indent=2, allow_nan=False))
    if args.write_fixture:
        if failures:raise SystemExit("Reference comparison failed; fixture not published")
        atomic_text(args.write_fixture, json.dumps(report, indent=2, allow_nan=False))
    print(json.dumps({key: report[key] for key in ("comparisons", "maximum_absolute_error", "failures", "passed")}))
    return int(bool(failures))


if __name__ == "__main__":
    raise SystemExit(main())
