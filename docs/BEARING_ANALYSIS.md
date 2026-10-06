# Bearing duty and capacity

Version 1.0.0rc6 adds original basic bearing-fatigue arithmetic linked to the
explicit shaft load path. Capacities, factors and operating limits are entered
for each selected bearing; the app does not substitute the search engine's generic
bearing table. This is a component assessment under declared conditions, not a
production gearbox service-life rating or a claim of standards compliance.

## Desktop and batch workflow

Open **Design → Bearing duty and capacity…**, or choose **Assess bearings…** in a
shaft study. The complete shaft input is copied into the bearing study. Each
assessment recalculates that load path, including all duty cases and the axial
locating bearing. The original shaft file is not modified or automatically synced.

1. Set the manufacturer, exact designation, bearing type, bore, basic dynamic
   capacity C and static capacity C0 for bearings A and B.
2. Enter the applicable speed, minimum load, axial load, temperature and
   misalignment limits, together with the required static safety factor. These
   must apply to the actual lubricant, clearance, arrangement and operating range.
3. Record source/revision/location, applicable rating conditions and the basis
   for redistributing any supplied data. Source declarations are not approval.
4. For every shaft duty case and bearing, enter bearing operating temperature and
   installation/housing-axis error. Ambient temperature is not substituted.
5. For combined radial/axial loading, enter the case-specific dynamic X/Y and
   static X0/Y0 factors and their applicable branch/conditions. No supplier factor
   table is inferred. Pure radial loading uses the radial force directly.
6. Calculate and review every limit check, per-case fatigue contribution and
   repeated-duty total. Include startup, reverse, overload and stationary peak
   loads as explicit shaft cases with appropriate forces and durations.
7. Save `.gearforge-bearing` and export the input, calculation JSON, HTML report
   and integrity manifest. **New from shaft…** starts fresh definitions/factors;
   it does not reuse factors against changed load cases.

Blank values are saved as explicit unknowns. Missing capacities or combined-load
factors prevent the corresponding life calculation. Missing operating limits
remain `unassessed`, even when some arithmetic can be evaluated. Editing any
input invalidates the old desktop result. Synthetic examples never become a
supplier selection or an approved design.

```text
python -m gearforge bearing new blank.gearforge-bearing
python -m gearforge bearing new example.gearforge-bearing --synthetic-example
python -m gearforge bearing from-shaft shaft.gearforge-shaft --out bearings.gearforge-bearing
python -m gearforge bearing calculate bearings.gearforge-bearing --out bearing-assessment
python -m gearforge verify bearing-assessment
```

The ordinary calculation/export command can produce a labeled incomplete
assessment. Its successful exit means the assessment was exported, not that
its checks passed. Automated users must inspect the per-bearing assessment and
individual check states in `calculation.json`. `production_approved` remains false
and `rated_gearbox_life_hours` remains null for every result.

## Method: basic-bearing-duty-1

Let Fr and Fa be magnitudes from the recalculated shaft reactions. For radial
load alone, P = P0 = Fr. For a deep-groove ball bearing with axial loading, the
implemented radial-envelope forms are:

```text
P  = max(Fr, X Fr + Y Fa)
P0 = max(Fr, X0 Fr + Y0 Fa)
L10_revolutions = 1,000,000 (C/P)^p
s0 = C0/P0
```

The radial envelope retains Fr as a lower bound. Enter factors for the actual
load ratio, bearing design and clearance; the envelope does not validate the
chosen supplier branch. Exponent p is 3 for the supported radial ball model and
10/3 for the radial-only cylindrical-roller model. Any axial reaction makes the
cylindrical-roller model unsupported; flange load capacity is not inferred.

For piecewise-constant duty case i, with duration hi in hours and shaft speed ni
in rpm, GearForge calculates:

```text
Ni = 60 abs(ni) hi
Di = Ni / 1,000,000 × (Pi/C)^p
Dcycle = sum(Di)
Tcycle = sum(hi)
Basic repeated-duty L10 hours = Tcycle / Dcycle
Damage at requested duration H = Dcycle × H/Tcycle
```

This is also obtained by a revolution-weighted equivalent load, with
`Peq^p = sum(Ni Pi^p)/sum(Ni)` and mean absolute speed
`nmean = sum(abs(ni) hi)/Tcycle`. Reversals never cancel fatigue exposure.
Stationary cases contribute zero rolling revolutions, while their full load
still receives a static check. Dynamic combined-load factors are not required
for a stationary case; static factors remain necessary under axial loading.
An oscillating case makes rolling life unavailable because rpm alone does not
define contact exposure. Zero fatigue demand or numerical overflow is represented
by null life, never by an infinite physical-life claim.

Static load is checked as `P0 <= C0 / required_s0` in every case, so a short peak
cannot disappear into a fatigue average. Speed uses its absolute value. The
misalignment check conservatively adds shaft-slope magnitude to the entered
installation/housing-axis error magnitude. Nominal bore is compared with the
shaft diameter at the point support; a diameter discontinuity there is ambiguous
and remains unassessed. Seat width, fit and bearing/housing flexibility need a
manufacturing and assembly model.

The complete nested shaft, both bearing definitions, every condition/factor,
requested duration and notes are included in the input fingerprint. The report
contains full inputs and source declarations. A manifest verifies integrity,
not authorship, suitability of supplier data or engineering approval.

## Verification and public distribution

`scripts/verify_bearing_reference.py` creates separate closed-form reactions and
60-digit Decimal calculations for seven GearForge-authored synthetic cases. Its
218 comparisons cover radial/combined loading, the radial envelope, both
exponents, asymmetric supports/load positions, reversals, variable duty,
stationary peaks and zero load. Relative tolerance is 1e-10 and absolute tolerance
1e-12. The initial largest relative discrepancy was below 3.7e-15.

This is an independent arithmetic implementation, **not** an independent bearing
rating package or physical-life validation. It does not verify supplier factors,
material fatigue distributions or lubrication conditions. Unit tests also cover
missing/invalid data, unsupported motion/type, input identity, source
recalculation, unknown temperatures, save failures, UI invalidation and export
integrity. CI regenerates the arithmetic comparison on all three platforms.

```text
python scripts/verify_bearing_reference.py
python -m pytest tests/test_bearings.py -q
```

The offline fixture is `tests/data/open_bearing_reference.json`; the supplied
`.gearforge-bearing` example contains invented ratings clearly labeled synthetic.
All implementation, adapter and example data were authored for GearForge under
Apache-2.0. The verifier uses the Python standard library and existing app
dependencies. No manufacturer table, proprietary standard text, supplier figure
or restricted worked example is copied into the repository.

Public primary references describe the mathematical relationships and their
engineering context. They are linked reading material, not redistributed content
or requirements for access to a paid standard:

- [Schaeffler Technical Pocket Guide](https://www.schaeffler.com/remotemedien/media/_shared_media/08_media_library/01_publications/schaeffler_2/catalogue_1/downloads_6/stt_de_en.pdf):
  basic fatigue relationships and equivalent stepped operating values.
- [SKF bearing selection reference](https://www.skf.com/binaries/pub12/Images/0901d196807026e8-100-700_SKF_bearings_and_mounted_products_2018_tcm_12-314117.pdf):
  static/peak-load checks and the limits of calculated fatigue life.

## Remaining production work

Basic L10 describes 90% survival for an idealized population of one bearing
under the model's conditions. It does not establish a particular bearing's
life, pair reliability, gearbox reliability or a warranty. In particular:

- Lubrication, contamination, temperature-dependent capacity, seal/cage wear,
  fretting, false brinelling and actual heat balance need separate assessment.
- Supplier minimum-load and maximum-speed limits depend on more than one scalar.
  The entered limits must be conservative for all declared conditions.
- Angular-contact/tapered arrangements, preload, induced thrust and load sharing
  require an arrangement model; they cannot be selected through this model.
- Shaft/housing compliance, thermal growth, retention, shoulders, fits and
  clearances must be established by the real assembly design.
- Structured supplier/material evidence, independent review and representative
  physical tests remain necessary for a production release.

See [production qualification](PRODUCTION_QUALIFICATION.md) for the full scope.
