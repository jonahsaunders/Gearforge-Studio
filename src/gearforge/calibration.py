from __future__ import annotations

from dataclasses import replace
from .models import PrintProfile, finite


def calibrate_profile(profile: PrintProfile, measured_outer_mm: float, nominal_outer_mm: float,
                      measured_bore_mm: float, nominal_bore_mm: float, evidence: str):
    """Infer uniform XY shrink and residual bore bias from a paired coupon.

    No strength is inferred from dimensional measurements. Coupon measurement
    uncertainty, anisotropy and actual bearing fits remain user-reviewed.
    """
    measured_outer_mm = finite(measured_outer_mm,"Measured outside",1,500)
    nominal_outer_mm = finite(nominal_outer_mm,"Nominal outside",1,500)
    measured_bore_mm = finite(measured_bore_mm,"Measured bore",1,100)
    nominal_bore_mm = finite(nominal_bore_mm,"Nominal bore",1,100)
    shrink = (1-measured_outer_mm/nominal_outer_mm)*100
    bore_compensation = nominal_bore_mm * measured_outer_mm / nominal_outer_mm - measured_bore_mm
    result = replace(profile,shrink_percent=shrink,bore_compensation_mm=bore_compensation,
                     test_evidence=(profile.test_evidence+"\nDimensional coupon: "+evidence).strip())
    result.validate()
    return result


def export_coupon(path, nominal_outer_mm=40., nominal_bore_mm=10.):
    import cadquery as cq
    from pathlib import Path
    path = Path(path)
    if path.exists():
        raise FileExistsError("Coupon output already exists")
    outer = finite(nominal_outer_mm,"Outside",20,100)
    bore = finite(nominal_bore_mm,"Bore",3,30)
    if bore >= outer-6:
        raise ValueError("Coupon needs at least 3 mm of wall")
    coupon = cq.Workplane("XY").rect(outer,outer).circle(bore/2).extrude(6)
    cq.exporters.export(coupon,str(path),tolerance=.03)
