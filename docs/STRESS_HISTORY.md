# Local stress histories and cyclic fatigue

GearForge implements the cycle counter, arithmetic, editor, exports and fixtures
as original Apache-2.0 code/data suitable for this public GitHub repository.
No paid standard, restricted material table or private solver is required.
The separate verification environment uses MIT-licensed `rainflow` 3.2.0; it is
not an application dependency. This work makes no ASTM, ISO or AGMA conformance claim.

## What this study covers

The study counts an ordered history of **signed local normal stress at one fixed
physical material point and direction**. It can assess bounded, user-declared
uniaxial elastic fatigue data with a selected mean-stress correction and linear
Miner accumulation. Starts, stops, reversals and overloads must appear in the
supplied samples and explicit transitions; entering a start count does not
invent its stress waveform. Sampling must resolve all relevant stress extrema.

A gear torque spectrum alone is not a local stress history. The existing root
solver's sampled pressure-patch peaks and positive von Mises values are not
automatically converted to signed cyclic stress. A validated complete moving-load
solution or measured history is still needed before this layer can support
component fatigue qualification. Histories from different points, changing
principal directions or a multiaxial state cannot be mixed into one study.

## Desktop and batch use

Open **Design → Cyclic stress history and fatigue…**, or transfer retained duty
from **Engineering study → Study stress history…**. Seven tabs retain the point
definition/method, material/curve, ordered blocks, selected block samples, plots,
assessment and source gear duty. The synthetic example demonstrates arithmetic;
its waveform, material properties and limit are invented, not engineering allowables.

Each block has a name, retained duty case, integer repetition count, starts per
repeat, data status, source/revision, applicability and redistribution basis.
Rows define chronological order. Select a row to edit its samples; moving a row
also moves its samples and import fingerprints. Invalid in-progress sample text
is retained when switching rows. A failed save leaves the editor and prior path intact.

Sample CSV is UTF-8 (an initial BOM is accepted), with exactly:

```csv
time_s,stress_mpa
0,0
0.01,100
0.04,0
```

Time starts at zero, strictly increases and uses seconds. Stress is signed MPa.
Blank blocks are unknown, not unloaded. Repeated blocks must end at their starting
stress. Adjacent blocks must share the same endpoint stress: supply an explicit
transition block when needed. There is no implied ramp, jump, zero return or
cyclic wrapping of the entire study. The last residual is finite.

Import records both the raw file SHA-256 and canonical parsed-sample SHA-256.
Subsequent edits are reported as differing from the import. These are integrity
identifiers, not independent review or evidence of permission to redistribute.
Save original source CSV separately if its exact original bytes are needed.

```text
python -m gearforge history new local.gearforge-history
python -m gearforge history new example.gearforge-history --synthetic-example
python -m gearforge history from-study target.gearforge-study --out local.gearforge-history
python -m gearforge history import-csv local.gearforge-history samples.csv --block "History block" --out imported.gearforge-history
python -m gearforge history calculate example.gearforge-history --out history-assessment
python -m gearforge verify history-assessment
```

Choose a new path for each command that creates a study or assessment. Inputs
use strict versioned `.gearforge-history` JSON; unknown fields and nonfinite
numbers are rejected. An assessment contains editable inputs, calculation JSON,
HTML, exact cycle-bin CSV, unexpanded template-sample CSV and a SHA-256 manifest.
Calculation/export run in cancellable subprocesses in the desktop.

## Method: finite-uniaxial-history-1

Consecutive equal samples are collapsed; changes of direction produce reversals.
For consecutive reversals A,B,C,D, the B–C range closes a full cycle when it is
no larger than either adjacent A–B or C–D range. Remove B,C and reconsider the
remaining tail. Only after all blocks and repetitions are processed are adjacent
remaining reversals counted as half cycles. Thus cross-block closures and finite
endpoint halves survive. Nonzero ranges retain exact minimum, maximum, mean and
integer half-cycle counts. No amplitude binning, rounding or noise filter changes
the count. Zero-range plateaus contribute no fatigue cycles.

For repeated closed blocks, acceleration begins only when the complete streaming
state repeats: reversal stack, last sample and pending direction. Cycles emitted
between identical states are multiplied by an integer number of remaining loops.
The residual state stays intact for subsequent blocks. This is not independent
per-block counting or a stationary-cycle approximation. Failure to repeat within
eight passes fails closed. Limits: 200 blocks, 100,000 total stored samples,
1e12 repetitions per block, and 1e15 expanded samples including shared endpoints.
The counter's operation and memory remain bounded by stored inputs.

Times determine duty coverage, not rainflow amplitude. Per-case duration equals
the sum of each template's final time times repetitions. It must match retained
hours within relative 1e-9/absolute 1 microsecond; start totals must match exactly.
Numeric damage can describe a partial entered history, but that is visibly
separate from complete retained duty coverage.

Let `f ≥ 1` be the explicit stress factor. For each counted minimum/maximum pair:

```text
amplitude = f (maximum - minimum) / 2
mean      = f (maximum + minimum) / 2
```

`fully_reversed_only` accepts zero mean within a relative 1e-12 numerical tolerance.
`goodman_tension_only` requires entered ultimate tensile strength `Su` and uses:

```text
equivalent amplitude = amplitude / (1 - max(mean, 0) / Su)
```

Tensile mean reaching `Su` is unsupported. Compressive mean gets no beneficial
credit. The complete factored signed history must remain within the entered
positive/negative local elastic limit. The declared S-N curve must be entirely
within that elastic limit and applicable over the full entered local temperature
range. A user must substantiate the selected correction for the actual material,
process, surface, environment and stress state; the software does not infer that
applicability from material designation.

The S-N curve contains 2–50 **fully reversed local stress amplitudes versus cycles
to the declared failure endpoint**. Failure cycles strictly increase and amplitudes
strictly decrease. Runouts are not failure points. The model interpolates linearly
in log(amplitude) versus log(failure cycles), including the exact endpoints.
It never extrapolates, invents an endurance limit, or turns a below-curve cycle
into zero damage. Survival/confidence inputs describe the supplied curve; the app
does not transform median data into reliability-adjusted allowables.

Linear damage is `sum(count / failure_cycles)`, including finite half cycles.
If any cycle is outside the entered curve or unsupported mean-stress model,
total damage is unavailable. Supported contributions remain as a lower bound
**within this arithmetic model**. The entered threshold is explicit; no default
acceptance at damage 1 is applied. An incomplete sum can demonstrate threshold
exceedance but cannot demonstrate acceptance. No remaining-life extrapolation or
rated gearbox life is produced, including for a constant-stress history.

## Independent numerical verification

Install the reference in a separate environment, then run the original adapter:

```text
python -m venv reference-history
reference-history/Scripts/python -m pip install -r scripts/requirements-history-reference.txt
python scripts/verify_history_reference.py --reference-python reference-history/Scripts/python
```

Use `reference-history/bin/python` on Linux/macOS. The reference subprocess imports
`rainflow` only, expands finite histories and calls its public `extract_cycles` API.
It does not import GearForge. The fixture covers 414 original histories, nested
loops, plateaus, finite half cycles, changing block boundaries, repetitions and
smooth signals. The reference omits two-sample histories, so the adapter appends
an identical terminal sample in that case; this adds no stress excursion. It
discards zero-range reference plateaus. That adaptation is recorded in the results.

A separate original 60-digit Decimal implementation checks the tensile-only mean
correction, log S-N interpolation and accumulated damage at three stress factors.
The recorded comparison contains 25,788 checks; all pass. Maximum relative
arithmetic difference is about 2.6e-15. Exact endpoint pairs and integer half-cycle
counts match the reference. These are algorithm checks, not fatigue experiments.
The original synthetic 10,000-hour example represents 5,400,000,001 samples and
produces damage approximately 0.1631041131 against an invented limit of 0.5.

Reference: [rainflow 3.2.0 public API](https://pypi.org/project/rainflow/3.2.0/) and
[MIT license](https://github.com/iamlikeme/rainflow/blob/main/LICENSE.txt), Copyright
(c) 2018 Piotr Janiszewski. Its source/license remain in the separate installation.
No third-party implementation, standard text or measured material table is bundled.

## Qualification boundary

Correct cycle extraction does not make linear Miner damage sequence-sensitive.
Plasticity, residual-stress evolution, multiaxiality, fretting, wear, corrosion,
thermomechanical fatigue and load interaction are not modeled. Source sampling,
model/measurement accuracy and the physical point/direction require verification.
The app records declarations and coverage separately from numeric applicability.
Even complete declared evidence and damage below the entered limit leave
`production_approved=false`, rated torque unavailable and rated gearbox life
unavailable. Component and assembly qualification still require actual material
evidence, independent review and physical load/life tests.
