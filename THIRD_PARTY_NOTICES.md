# Third-party notices

GearForge application code is Apache-2.0. Third-party packages retain their licenses.
No supplier logo or manufacturer CAD file is redistributed. Seed dimensional/rating
facts identify KHK as their source; trademarks remain with their owners. Supplier
website price/stock values are not embedded or fabricated.

Core dependencies:

| Dependency | Upstream license family | Distribution note |
| --- | --- | --- |
| CadQuery | Apache-2.0 | Retain license/notices |
| cadquery-ocp / Open CASCADE | LGPL-2.1 with exception (upstream) | Retain exact wheel license and comply with applicable terms |
| PySide6-Essentials / Shiboken6 / Qt | LGPL-3.0 / GPL / commercial options | Retain exact distribution notices and applicable LGPL obligations |
| NumPy | BSD-3-Clause | Retain license |
| VTK | BSD-style | Retain license |
| ReportLab | BSD-style | Retain license |
| ezdxf | MIT | Retain license |
| CasADi / NLopt and native transitive libraries | Various, including LGPL | Inspect exact package licenses for distributed build |

The native build tooling collects installed dependency license files into
`licenses/` in the bundle. This table is a guide, not a replacement for those files or
a complete legal audit. Check the exact dependency lock and binary composition for
the target release. No commercial Qt license is supplied by this project.

Collection follows the full installed runtime dependency graph, including
SciPy, Numba, llvmlite and the Trame dependency chain. `DEPENDENCIES.json` records
package versions, license metadata, upstream URLs and copied texts;
`requirements-runtime.txt` records the resolved versions. The release workflow
adds a vulnerability report and CycloneDX SBOM. This inventory conservatively
includes declared dependencies even when their modules are excluded from the
frozen application. Standard Apache-2.0 text supplements the proxy wheel whose
metadata declares that license but omits its text.

PySide6/Qt is used under its applicable open-source license terms. Recipients
retain the rights granted by those terms. Keep notices and applicable library
source/replacement information with the deployment. See
https://www.qt.io/development/open-source-lgpl-obligations for upstream guidance;
the company must review the exact deployment and any additional distribution.

The optional engineering verification script runs a separately checked-out
[FreeCAD Gears](https://github.com/looooo/freecad.gears) (GPL-3.0-or-later) at commit
`83ec154b1925347622b61812f75d2ed51e956b9f`. That project's source is not copied into,
installed with or bundled in GearForge. The repository stores numerical outputs
from GearForge-authored synthetic inputs and the reproducible comparison adapter.
Those comparisons cover specific geometry quantities, not gearbox load ratings.

The analytical engineering module is an original implementation. Linked KHK
technical pages are public reading material, not declared open-source content;
their document text, figures and tables are not redistributed. No proprietary
standard text, standard factor table or restricted reference result is bundled.

The optional shaft comparison uses [PyNiteFEA 3.2.0](https://github.com/JWock82/Pynite),
licensed MIT, in a separate verification environment. Its source and dependencies
are not included in the application build. The bundled shaft fixture contains
GearForge-authored synthetic inputs and numerical results. The adapter uses the
reference's public API; it does not copy the finite-element implementation.

Primary technical/source references:

- https://cadquery.readthedocs.io/en/stable/
- https://doc.qt.io/qtforpython-6/
- https://catalog.khkgears.us/item/spur-gears/spur-gears-ss/ss1-20
- https://catalog.khkgears.us/item/spur-gears/spur-gears-ss/ss1-30
- https://catalog.khkgears.us/item/spur-gears/spur-gears-ss/ss1-40
- https://catalog.khkgears.us/item/spur-gears/spur-gears-ss/ss1-60
- https://www.khkgears.us/catalog/product/SSG1-40
- https://www.khkgears.us/catalog/product/MSGA1-40
- https://khkgears.net/pdf/spur-tech.pdf

The bearing assessment and high-precision verification adapter are original
GearForge implementations. The adapter uses Python standard-library Decimal.
Bundled capacities/factors are synthetic, not a manufacturer product table.
Linked Schaeffler/SKF documents provide public mathematical context; their text,
tables and figures are not redistributed. No paid standard is required.

## Open shaft fatigue method reference

The original `fatigue.py` implementation and benchmark adapter use mathematical
relations and numerical example inputs from Stuart H. Loewenthal, NASA RP-1123
(1984), printed pages 17–19. [NTRS](https://ntrs.nasa.gov/citations/19840018973)
identifies the NASA-authored work as US-government work with public use permitted.
The scanned report, third-party figures and material/factor tables are not
bundled. Original source, tests and adapter code remain Apache-2.0. Historical
example values are not material allowables. See `docs/SHAFT_FATIGUE.md`.

## Open tooth-contact comparison reference

The original Hertz implementation and numerical fixtures use a separately checked
out [SlipPY](https://github.com/FrictionTribologyEnigma/slippy) reference, revision
`a4fbb447fc494d0480661ee41ef15fdc82e7423c`, MIT License, Copyright (c) 2018
FrictionTribologyEnigma. The original adapter invokes its documented line-contact
API in a separate process. No SlipPY source, documentation or runtime dependency
is bundled. The reference checkout retains its MIT license. GearForge-authored
inputs and numerical result fixtures are distributed under Apache-2.0. No pressure-
life data in the synthetic example represents a supplier or measured material.
See [contact methods and reproduction](docs/CONTACT_ANALYSIS.md).
