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
