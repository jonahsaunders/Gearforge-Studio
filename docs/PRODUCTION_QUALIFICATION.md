# Production design and load-rating gap

**Status: not qualified for final production gearbox design or service-load
ratings.** The requested commercial outcome is not yet achieved. Version
1.0.0rc3 improves software reliability, deployment and traceability; it does not
turn the existing screening equations into a validated rating method.

## Current numerical boundary

`available_output_nm` is motor capability multiplied by reduction and assumed
efficiency. It is not the torque the gears, shafts, bearings, housing or retention
can safely transmit for a stated life. Required life is an input to a generic
bearing screen, not a validated life rating for the gearbox.

The implementation uses a Lewis tooth-bending approximation, illustrative printed
material allowables, an assumed shaft allowable, generic bearing capacities and
assumed efficiencies. Catalog ratings are conditional supplier values. Free-form
print-profile evidence text is not verified material test data. Static and
12-pose CAD checks cannot establish continuous contact or cumulative tolerances.

Every new design export contains `qualification.json`, with
`production_approved: false`, `rated_output_torque_nm: null`, a separate motor
capability value and explicit engineering blockers. The manifest also records
the unavailable production rating. Automated consumers can require a rating:

```text
python -m gearforge qualify example.gearforge --out qualification.json
python -m gearforge export example.gearforge --out production-package --require-production-rating
```

`qualify` returns exit code 2 for an unqualified candidate; an invalid input or
calculation failure returns 1. Production-required export returns 1 and creates
no design directory. In this release **every family is unqualified**, including
commercial catalog designs. There is no checkbox or notes field that overrides
this. Ordinary export remains available for labeled prototypes and concepts.

## First production scope needed from the engineering owner

Define one initial qualified application rather than an unbounded claim:

- Gear family and topology, reduction, power, torque/speed envelope, starts,
  stops, reversals, shock loads and externally applied shaft loads.
- Materials, heat treatment or print/molding process, quality class, surface
  finish, lubrication, temperature/environment and dimensional constraints.
- Duty/load spectrum, required life, reliability, failure consequences and
  required calculation standards/editions and acceptance criteria.
- Actual gear/bearing supplier part numbers and rating conditions, material
  certificates, existing test results and an accountable engineering reviewer.

These application-specific values cannot be inferred from the example project.
Standards must be selected for the actual geometry, material and service. Full
authorized standards and reference cases are needed to implement and verify
their procedures; public abstracts are insufficient implementation specifications.

## Work packages and objective exit evidence

| Work package | Required implementation / evidence | Current state |
| --- | --- | --- |
| Design basis | Versioned operating envelope, load spectrum, environment, life/reliability and standard editions approved by the engineering owner | Application scope missing |
| Spur/helical rating | Applicable tooth-root fatigue and contact/pitting methods, geometry/material factors, load distribution, life/reliability factors, units and validity checks | Preliminary Lewis screen only |
| Planetary rating | Above plus internal ring, unequal load sharing, carrier/pin/bearing compliance and planet phasing | Unverified |
| Bevel, worm, cycloidal | Family-specific contact geometry and applicable rating methods, not a reused spur approximation | Concept search only |
| Materials | Traceable fatigue/contact/wear data over the qualified process, temperature, life and lubrication envelope; uncertainty and batch controls | Illustrative printed values / conditional catalog values |
| Full assembly | Bearings from actual supplier data, shaft fatigue, key/pin/clamp retention, housing/fasteners/mounts, external loads and tolerances | Generic screens / unmodeled failure modes |
| Thermal and tribology | Validated losses, temperature, lubrication, wear/creep and applicable scuffing limits across duty | Assumed efficiency; no validated thermal solver |
| Manufacturing | Production tooth/root definition, fit/tolerance stack, drawings, retention details, inspection and quality criteria | Sampled tooth CAD and reference layouts |
| Calculation verification | Independent worked cases, trusted reference results, tolerance-based comparisons, failure/boundary cases and independent review | Software regressions; no standards-rating verification |
| Product validation | Guarded qualification tests under a reviewed plan covering applicable loads, life, temperature, wear and representative manufacturing variation | Physical evidence unavailable |
| Engineering release | Controlled evidence linked to exact inputs, model version, manufacturing definition and reviewer approval; change-triggered requalification | Hash-traceable prototype packages only |

Do not implement a production-approved state until the selected scope has a
verified rating backend, structured traceable inputs, defensible acceptance
criteria and an independent engineering release process. A warning-only screen
must never become an implicit pass in that backend. Unsupported geometry or
missing allowables must fail closed, and changes to inputs, supplier records,
model version or manufacturing definition must invalidate prior approval.

## Primary method references

- [ISO 6336-1:2019](https://www.iso.org/standard/63819.html) defines the basis and
  applicability of spur/helical load-capacity methods. It does not by itself
  assure the performance of an assembled gearbox. Other applicable parts cover
  individual failure modes and material factors.
- [ISO/TR 6336-30:2022](https://www.iso.org/standard/84147.html) supplies worked
  examples for specified ISO 6336 methods; example factors are not recommended
  criteria for a real design. Use authorized reference data for verification.
- [ISO 10300-1:2023](https://www.iso.org/standard/79401.html) addresses bevel gear
  load-capacity methods; this application's bevel concept is not an implementation.
- [AGMA 946-A21](https://members.agma.org/MyAGMA/MyAGMA/Store/Item_Detail.aspx?Category=STANDARDS&iProductCode=946_A21)
  describes plastic-gear test methods and documentation. A bulk material value
  or dimensional calibration coupon does not establish gear load capacity.

The referenced standards are not bundled, purchased, or implemented by this
change. Scope and evidence selection remain explicit engineering work.
