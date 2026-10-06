# Production design and load-rating gap

**Status: not qualified for final production gearbox design or service-load
ratings.** The requested commercial outcome is not yet achieved. Version
1.0.0rc10 includes open external spur/helical geometry, quasi-static forces,
operating duty, explicit shaft/bearing load paths and basic per-bearing fatigue
arithmetic against declared ratings, plus selected-section rotating-bending
and steady-torque shaft fatigue studies with explicit material evidence. Spur
Hertz contact studies now add explicit sharing and bounded pressure-life curves.
Thermal networks now resolve declared heat losses and cooling paths through
ordered phases and repeated cycles, with conservative warm-up bounds.
Rack-generated spur profiles now define rounded-cutter roots and their involute
joins, with analytic regularity checks and sampled manufacturing-study exports.
These do not establish gearbox fatigue
strength, adjusted bearing service life or production service-load ratings.

## Current numerical boundary

`available_output_nm` is motor capability multiplied by reduction and assumed
efficiency. It is not the torque the gears, shafts, bearings, housing or retention
can safely transmit for a stated life. Required life is an input to a generic
bearing screen, not a validated life rating for the gearbox.

The existing search uses a Lewis tooth-bending approximation, illustrative printed
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

## Agreed first development and qualification target

The first target is an enclosed steel spur reduction: **250 W, 1,500 rpm input,
5:1 reduction, 10,000 operating hours and 20–40 °C ambient**. Begin with continuous
duty, then add starts, reversals and overload cases; extend to two-stage and
helical assemblies after establishing the single-stage foundation. These values
define development work, not an approved product rating. The supplied 20/100-tooth,
module-2, 20-mm-face example is a calculation fixture, not a selected supplier design.

The app, tests and bundled evidence must be publishable on GitHub. The implementation
uses original analytical calculations and openly licensed comparison tools, with
no required access to proprietary standards, private software or restricted data.
See [open engineering methods and reproducible comparisons](OPEN_ENGINEERING.md).
Public manufacturer documents may be linked as context; their figures, text and
tables are not copied into the application or treated as openly licensed.

The engineering owner still needs to establish product-specific inputs:

- Gear family and topology, reduction, power, torque/speed envelope, starts,
  stops, reversals, shock loads and externally applied shaft loads.
- Materials, heat treatment or print/molding process, quality class, surface
  finish, lubrication, temperature/environment and dimensional constraints.
- Duty/load spectrum, required life, reliability, failure consequences and
  acceptance criteria and any contractual standards-compliance requirement.
- Actual gear/bearing supplier part numbers and rating conditions, material
  certificates, existing test results and an accountable engineering reviewer.

These application-specific values cannot be inferred from the example project.
Open analytical methods can be independently checked and physically validated
without a claim of compliance with a proprietary standard. If a future customer
requires compliance with a named standard, assess that requirement separately;
public abstracts are insufficient to implement or verify its complete procedure.

## Work packages and objective exit evidence

| Work package | Required implementation / evidence | Current state |
| --- | --- | --- |
| Design basis | Versioned operating envelope, load spectrum, environment, life/reliability and acceptance criteria | First development target agreed; editable geometry/duty study implemented; supplier/material details and acceptance criteria remain |
| Spur/helical rating | Applicable tooth-root fatigue and contact/pitting methods, geometry/material factors, load distribution, life/reliability factors, units and validity checks | Preliminary Lewis screen; open spur Hertz contact arithmetic and declared pressure-life curves added. Actual distribution, root fatigue, material durability and production tooth ratings remain unqualified |
| Planetary rating | Above plus internal ring, unequal load sharing, carrier/pin/bearing compliance and planet phasing | Unverified |
| Bevel, worm, cycloidal | Family-specific contact geometry and applicable rating methods, not a reused spur approximation | Concept search only |
| Materials | Traceable fatigue/contact/wear data over the qualified process, temperature, life and lubrication envelope; uncertainty and batch controls | Shaft fatigue studies retain explicit material evidence and curve bounds; no qualified material allowables supplied. Existing search still uses illustrative printed / conditional catalog values |
| Full assembly | Bearings from actual supplier data, shaft fatigue, key/pin/clamp retention, housing/fasteners/mounts, external loads and tolerances | Explicit shaft reactions/motion, bearing duty arithmetic and selected-section rotating-bending/steady-torque studies implemented; actual supplier selection, adjusted life, transient/whole-shaft fatigue, retention and housing remain |
| Thermal and tribology | Validated losses, temperature, lubrication, wear/creep and applicable scuffing limits across duty | Open passive thermal network, continuous extrema, energy balance and repeated-duty bounds implemented. Actual loss maps/cooling coefficients, nonlinear/local hot spots, lubrication and physical thermal validation remain |
| Manufacturing | Production tooth/root definition, fit/tolerance stack, drawings, retention details, inspection and quality criteria | Explicit rounded-rack spur root profiles, undercut/fold rejection, active-path checks and sampled DXF/SVG/CSV added; complete production drawings, tolerances, finishing and inspection remain. Prototype CAD still uses its earlier approximation |
| Calculation verification | Independent worked cases, trusted reference results, tolerance-based comparisons, failure/boundary cases and independent review | 72 geometry comparisons against FreeCAD Gears, 1,452 shaft comparisons against PyNiteFEA, 218 bearing arithmetic checks and 100 shaft-fatigue comparisons with independent arithmetic/public NASA example, and 208 Hertz comparisons against MIT SlipPY, and 3,539 thermal quantities against separate SciPy ODE/shooting calculations, and 266 root-profile rays against independent numerical cutter poses; no physical material-fatigue or assembly-rating qualification |
| Product validation | Guarded qualification tests under a reviewed plan covering applicable loads, life, temperature, wear and representative manufacturing variation | Physical evidence unavailable |
| Engineering release | Controlled evidence linked to exact inputs, model version, manufacturing definition and reviewer approval; change-triggered requalification | Hash-traceable prototype and engineering-study packages; no approval override |

Do not implement a production-approved state until the selected scope has a
verified rating backend, structured traceable inputs, defensible acceptance
criteria and an independent engineering release process. A warning-only screen
must never become an implicit pass in that backend. Unsupported geometry or
missing allowables must fail closed, and changes to inputs, supplier records,
model version or manufacturing definition must invalidate prior approval.

## Optional standards context

The references below describe established families of rating procedures. They are
not prerequisites for building or distributing GearForge and are not claimed as
implemented methods. Development follows the open-method route above.

- [ISO 6336-1:2019](https://www.iso.org/standard/63819.html) defines the basis and
  applicability of spur/helical load-capacity methods. It does not by itself
  assure the performance of an assembled gearbox. Other applicable parts cover
  individual failure modes and material factors.
- [ISO/TR 6336-30:2022](https://www.iso.org/standard/84147.html) supplies worked
  examples for specified ISO 6336 methods; example factors are not recommended
  criteria for a real design. These worked examples are not bundled or used as test fixtures.
- [ISO 10300-1:2023](https://www.iso.org/standard/79401.html) addresses bevel gear
  load-capacity methods; this application's bevel concept is not an implementation.
- [AGMA 946-A21](https://members.agma.org/MyAGMA/MyAGMA/Store/Item_Detail.aspx?Category=STANDARDS&iProductCode=946_A21)
  describes plastic-gear test methods and documentation. A bulk material value
  or dimensional calibration coupon does not establish gear load capacity.

The referenced standards are not bundled, purchased, or implemented by this
change. No restricted reference content is needed to reproduce the open comparisons.
