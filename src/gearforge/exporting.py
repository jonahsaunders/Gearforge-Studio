from __future__ import annotations

import csv
import hashlib
import html
import io
import json
import math
import os
import shutil
import tempfile
import zipfile
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from . import __version__
from .geometry import build_parts, collision_report, involute_outline
from .models import Candidate, PrintProfile, Requirements, atomic_text, candidate_from_dict


def safe_cell(value):
    if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@")):
        return "'" + value
    return value


def bom_csv(c: Candidate):
    output = io.StringIO()
    columns = ["part", "quantity", "source", "sku", "description", "material", "mass_g", "unit_cost", "currency", "url"]
    writer = csv.DictWriter(output, fieldnames=columns)
    writer.writeheader()
    writer.writerows({k: safe_cell(v) for k, v in row.items()} for row in c.bom)
    return output.getvalue()


def report_html(c: Candidate, req: Requirements, profile: PrintProfile, collisions=None):
    esc = lambda v: html.escape(str(v), quote=True)
    def rows(items):
        return "".join("<tr>"+"".join(f"<td>{esc(cell)}</td>" for cell in row)+"</tr>" for row in items)
    checkrows = "".join(f"<tr><td><span class='{esc(k.status)}'>{esc(k.status.upper())}</span></td><td>{esc(k.name)}</td><td>{esc('—' if k.value is None else f'{k.value:g}')} {esc(k.unit)}</td><td>{esc('—' if k.limit is None else f'{k.limit:g}')}</td><td>{esc(k.detail)}</td></tr>" for k in c.checks)
    warnings = "".join(f"<li>{esc(n)}</li>" for n in c.notes)
    requirement_rows = rows([(k, json.dumps(v) if isinstance(v, list) else v) for k,v in asdict(req).items()])
    stage_rows = rows([(i+1,s.driver.teeth,s.driven.teeth,f"{s.ratio:.5g}",f"{s.driver.module_mm:g}",f"{s.input_rpm:.1f}",f"{s.input_torque_nm:.4f}",f"{s.output_torque_nm:.4f}",f"{s.efficiency:.2%}") for i,s in enumerate(c.stages)])
    bomrows = rows([(b["part"], b["quantity"], b["source"], b["sku"], b["description"], "Unknown" if b["unit_cost"] is None else f"{b['unit_cost']:.2f} {b['currency']}") for b in c.bom])
    collision_section = "<p>Static CAD interference check has not been run. Full-cycle contact is unvalidated.</p>" if collisions is None else ("<p>No unexpected static interference found. Full-cycle contact is unvalidated.</p>" if not collisions else "<table><tr><th>Part A</th><th>Part B</th><th>Overlap mm³</th><th>Status</th></tr>"+rows([(r["a"],r["b"],r["overlap_mm3"],r["status"]) for r in collisions])+"</table>")
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>GearForge design {esc(c.id)}</title><style>
body{{font:15px system-ui,sans-serif;color:#243144;background:#f2f5f8;margin:0}}main{{max-width:1180px;margin:32px auto;background:white;padding:36px;border-radius:16px}}h1{{font-size:32px}}h2{{margin-top:32px}}.eyebrow{{color:#138c77;font-weight:700;letter-spacing:2px}}.banner{{padding:18px;background:#fff4df;border-left:4px solid #dc982f}}.metrics{{display:flex;gap:24px;margin:24px 0;flex-wrap:wrap}}.metrics b{{font-size:24px;display:block}}table{{border-collapse:collapse;width:100%;font-size:13px}}th,td{{text-align:left;padding:10px;border-bottom:1px solid #dfe5ee;vertical-align:top}}th{{background:#eef3f7}}.pass{{color:#087a58}}.warn{{color:#966107}}.fail{{color:#bd3849}}@media print{{body{{background:white}}main{{margin:0;padding:0}}tr{{break-inside:avoid}}}}
</style></head><body><main><div class="eyebrow">GEARFORGE STUDIO · {__version__}</div><h1>{esc(c.label)}</h1><p>Design {esc(c.id)} · {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}</p><div class="banner"><b>{'CONCEPT LAYOUT' if c.export_level == 'concept' else 'PROTOTYPE DESIGN'} — preliminary engineering screening.</b><br>Passing modeled checks does not establish a service-load rating or certify life, thermal behavior, housing strength, retention, manufactured fits or safety. Supplier conditions and physical verification are outstanding.</div><div class="metrics"><div><b>{c.ratio:.4g}:1</b>Reduction</div><div><b>{c.output_rpm:.1f} rpm</b>Output speed</div><div><b>{c.available_output_nm:.3f} N·m</b>Estimated available output</div><div><b>{c.efficiency:.0%}</b>Assumed efficiency</div><div><b>{c.backlash_deg:.3f}°</b>Estimated backlash</div></div><h2>Stages</h2><table><tr><th>Stage</th><th>Driver teeth</th><th>Driven teeth</th><th>Ratio</th><th>Module mm</th><th>Input rpm</th><th>Required input N·m</th><th>Output N·m</th><th>Efficiency</th></tr>{stage_rows}</table><h2>Checks and assumptions</h2><table><tr><th>Status</th><th>Check</th><th>Value</th><th>Limit</th><th>Method / limitations</th></tr>{checkrows}</table><h2>CAD interference</h2>{collision_section}<h2>Bill of materials</h2><p>Total cost: {esc('Unknown — quotations incomplete' if c.estimated_cost is None else c.estimated_cost)}. Printed-part masses are rough geometric estimates, not slicer predictions.</p><table><tr><th>Part</th><th>Qty</th><th>Source</th><th>SKU</th><th>Description</th><th>Unit cost</th></tr>{bomrows}</table><h2>Design notes</h2><ul>{warnings}</ul><h2>Print profile</h2><p>{esc(profile.name)} · allowable {profile.allowable_mpa:g} MPa · nozzle {profile.nozzle_mm:g} mm · layer {profile.layer_mm:g} mm</p><p>Evidence: {esc(profile.test_evidence or 'No test evidence attached')}</p><p>Orientation: {esc(profile.orientation)}. Nominal CAD uses compensation on printed bores and bearing seats. Shrink compensation {profile.shrink_percent:g}% is applied only to exported print-local meshes.</p><h2>Requirements</h2><table>{requirement_rows}</table><h2>References and methods</h2><p>Supplier sources are recorded per catalog item. Tooth bending uses a preliminary Lewis model. Shaft stress combines elastic bending and torsion. Bearing life uses basic ball-bearing L10 with generic assumed ratings. Detailed ISO/AGMA fatigue and contact rating, wear, creep and thermal models have not been implemented.</p><p>Generated tooth roots use sampled radial relief rather than a cutter-generated trochoid. Assembly preview and static interference checks do not validate full-cycle meshing.</p></main></body></html>"""


def drawing_svg(c: Candidate):
    sx, sy, sz = c.size_mm
    margin = 35
    header = f'<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="900" viewBox="{-margin} {-margin} {sx+2*margin} {sy+2*margin+30}"><rect x="{-margin}" y="{-margin}" width="{sx+2*margin}" height="{sy+2*margin+30}" fill="white"/><g stroke="#526477" stroke-width="0.5" fill="none"><rect width="{sx}" height="{sy}"/>'
    paths = []
    if c.export_level != "concept":
        for item in c.layout:
            s = c.stages[item["stage"]]
            gear = s.planet if item["role"] == "planet" else (s.driver if item["role"] == "driver" else s.driven)
            points = involute_outline(gear.teeth, gear.module_mm, gear.pressure_deg, .1, gear.helix_deg, gear.internal)
            angle = math.radians(item["rotation_deg"])
            transformed = [(x*math.cos(angle)-y*math.sin(angle)+item["x"],x*math.sin(angle)+y*math.cos(angle)+item["y"]) for x,y in points]
            d = "M" + " L".join(f"{x:.3f},{y:.3f}" for x,y in transformed) + " Z"
            paths.append(f'<path d="{d}" stroke="#17a68a" fill="#17a68a" fill-opacity="0.06"/>')
            if gear.internal:
                paths.append(f'<circle cx="{item["x"]}" cy="{item["y"]}" r="{gear.outer_mm/2}"/>')
            else:
                paths.append(f'<circle cx="{item["x"]}" cy="{item["y"]}" r="{gear.bore_mm/2}"/>')
    else:
        paths.append(f'<circle cx="{sx/2}" cy="{sy/2}" r="{min(sx,sy)/2-15}" stroke-dasharray="3 2"/>')
    footer = f'</g><g fill="#26384a" font-family="sans-serif" font-size="5"><text x="0" y="-15">GEARFORGE · {c.family.upper()} · {c.ratio:.4g}:1 · {c.id}</text><text x="0" y="{sy+10}">Envelope {sx:.2f} × {sy:.2f} × {sz:.2f} mm. Top layout only; nominal dimensions.</text><text x="0" y="{sy+20}">PROTOTYPE / CONCEPT · verify fits, retention and full-cycle meshing before manufacture.</text></g></svg>'
    return header + "".join(paths) + footer


def shaft_drawings_svg(c: Candidate):
    rows = []
    for i, shaft in enumerate(c.shafts):
        y = 70+i*110
        d = shaft["diameter"]
        length = c.size_mm[2]+24 if c.family != "planetary" else (21+c.stages[0].driver.width_mm+11 if i == 0 else c.size_mm[2]-c.stages[0].driver.width_mm)
        scale = min(4, 600/max(length,1))
        rows.append(f'<text x="35" y="{y-15}">Shaft {i+1}: Ø{d:g} × {length:.2f} mm · steel · {shaft["bearing"]["sku"]} bearing seat</text><rect x="35" y="{y}" width="{length*scale}" height="{d*scale}" fill="none" stroke="#33475b"/><line x1="25" y1="{y+d*scale/2}" x2="{45+length*scale}" y2="{y+d*scale/2}" stroke="#7b8da2" stroke-dasharray="5 4"/>')
    return f'<svg xmlns="http://www.w3.org/2000/svg" width="900" height="{max(300, len(c.shafts)*110+130)}"><rect width="100%" height="100%" fill="white"/><g font-family="sans-serif" font-size="15" fill="#26384a"><text x="35" y="30">GearForge shaft schedule — nominal reference, not a production drawing</text>{"".join(rows)}<text x="35" y="{len(c.shafts)*110+90}">Pin bores are in STEP. Bearing fits, keyways, collars and retention require design review.</text></g></svg>'


def write_pdf(path: Path, c: Candidate, req: Requirements, profile: PrintProfile):
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
    styles = getSampleStyleSheet()
    esc = lambda s: html.escape(str(s))
    doc = SimpleDocTemplate(str(path), pagesize=(210*mm,297*mm), rightMargin=16*mm, leftMargin=16*mm)
    flow = [Paragraph("GEARFORGE STUDIO",styles["Title"]), Paragraph(esc(c.label),styles["Heading1"]),
            Paragraph(f"Design {c.id} | {__version__} | PROTOTYPE / PRELIMINARY SCREEN",styles["Normal"]), Spacer(1,6*mm),
            Paragraph("Passing modeled checks does not certify service loads, fatigue life, thermal performance, manufactured fit or retention. Supplier rating conditions and physical validation remain outstanding.",styles["Normal"]), Spacer(1,5*mm)]
    flow.append(Table([["Reduction",f"{c.ratio:.4g}:1"],["Output speed",f"{c.output_rpm:.1f} rpm"],["Available output",f"{c.available_output_nm:.3f} N m"],["Assumed efficiency",f"{c.efficiency:.0%}"],["Envelope", " x ".join(f"{v:.1f}" for v in c.size_mm)+" mm"]],colWidths=[60*mm,110*mm]))
    flow.append(Paragraph("Checks and assumptions",styles["Heading2"]))
    for check in c.checks:
        val = "Uncharacterized" if check.value is None else f"{check.value:g} {check.unit}; limit {check.limit}"
        flow.append(Paragraph(f"<b>{esc(check.status.upper())} - {esc(check.name)}</b>: {esc(val)}<br/>{esc(check.detail)}",styles["Normal"]))
        flow.append(Spacer(1,3*mm))
    flow.extend([PageBreak(),Paragraph("Bill of materials",styles["Heading1"])])
    for row in c.bom:
        flow.append(Paragraph(f"<b>{esc(row['part'])}</b> x {row['quantity']} - {esc(row['source'])} {esc(row['sku'])}<br/>{esc(row['description'])}",styles["Normal"]))
        flow.append(Spacer(1,3*mm))
    flow.append(Paragraph("Profile and evidence",styles["Heading2"]))
    flow.append(Paragraph(esc(profile.name)+"<br/>"+esc(profile.test_evidence or "No physical test evidence attached."),styles["Normal"]))
    for note in c.notes:
        flow.append(Paragraph(esc(note),styles["Normal"]))
    def page(canvas, doc):
        canvas.setFont("Helvetica",8)
        canvas.setFillColor(colors.HexColor("#5c6e83"))
        canvas.drawString(16*mm,12*mm,f"GearForge {c.id} - preliminary design")
        canvas.drawRightString(194*mm,12*mm,str(doc.page))
    doc.build(flow,onFirstPage=page,onLaterPages=page)


def export_bundle(candidate: dict, requirements: dict, profile: dict, destination: str, include_cad=True):
    """Publish a complete directory atomically. Never overwrite user files."""
    from .models import Project
    c, req, p = candidate_from_dict(candidate), Requirements(**requirements), PrintProfile(**profile)
    req.validate()
    p.validate()
    dest = Path(destination).resolve()
    if dest.exists():
        raise FileExistsError("Choose a new export folder; existing files will not be overwritten")
    dest.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=".gearforge-export-",dir=dest.parent))
    try:
        collisions = None
        if include_cad and c.export_level != "concept":
            import cadquery as cq
            parts = build_parts(c, req, p)
            collisions = collision_report(parts)
            interference = [r for r in collisions if r["status"] == "interference"]
            if interference:
                raise ValueError("Unexpected static interference: "+", ".join(f"{r['a']} / {r['b']}" for r in interference)+". Export report-only and review geometry.")
            assembled = cq.Assembly(name="GearForge_"+c.id)
            step_dir, print_dir = temporary/"step", temporary/"print"
            step_dir.mkdir()
            print_dir.mkdir()
            for part in parts:
                assembled.add(part.shape,name=part.name,color=cq.Color(*part.color))
                cq.exporters.export(part.shape,str(step_dir/(part.name+".step")))
                if part.source == "print":
                    shape = part.shape.translate(tuple(-v for v in part.center))
                    zmin = shape.val().BoundingBox().zmin
                    shape = shape.translate((0,0,-zmin))
                    if p.shrink_percent:
                        shape = cq.Workplane(obj=shape.val().scale(1/(1-p.shrink_percent/100)))
                    for extension in ("stl","3mf"):
                        cq.exporters.export(shape,str(print_dir/(part.name+"."+extension)),tolerance=0.04,angularTolerance=0.12)
            assembled.export(str(temporary/"assembly.step"))
            atomic_text(temporary/"cad-interference.json",json.dumps(collisions,indent=2))
        Project(name=c.label,requirements=req,profile=p,selected_id=c.id,design_snapshot=asdict(c)).save(temporary/"design.gearforge")
        atomic_text(temporary/"bom.csv",bom_csv(c))
        from .simulation import operating_sweep
        sweep=operating_sweep(c,req)
        atomic_text(temporary/"simulation-sweep.json",json.dumps(sweep,indent=2,allow_nan=False))
        keys=("input_rpm","output_rpm","motor_torque_nm","available_output_nm","input_power_w","output_power_w","loss_power_w","load_margin_nm","status")
        stream=io.StringIO();writer=csv.DictWriter(stream,fieldnames=keys,extrasaction="ignore");writer.writeheader();writer.writerows(sweep["points"])
        atomic_text(temporary/"simulation-sweep.csv",stream.getvalue())
        atomic_text(temporary/"report.html",report_html(c,req,p,collisions))
        write_pdf(temporary/"report.pdf",c,req,p)
        atomic_text(temporary/"layout.svg",drawing_svg(c))
        atomic_text(temporary/"shafts.svg",shaft_drawings_svg(c))
        assembly_text = f"""GEARFORGE {c.label} · {c.id}
PROTOTYPE / PRELIMINARY DESIGN

1. Review report.html, all warnings, supplier rating conditions and CAD geometry.
2. Calibrate printed bores, bearing seats, backlash and shrink compensation using coupons.
3. Print gears flat. Inspect tooth surfaces, bores, pin holes and layer bonding.
4. Machine shafts from STEP, fit purchased bearings, add axial spacers and shaft collars.
5. Printed hubs use 3 mm cross pins. Catalog plain-bore gears require a reviewed
   keyway, cross-pin or clamping-hub modification; catalog geometry is reference only.
6. Install shafts and gears in the base. Verify axial gaps and free rotation.
7. Planetary builds additionally need carrier pin retention, planet bushings/spacers
   and a positive ring-to-housing torque attachment; these are unvalidated.
8. Install lid with M4 through bolts and captured nuts. Determine bolt lengths from CAD.
9. Perform a full-cycle low-speed meshing/clearance inspection. Establish lubrication.
10. Conduct guarded unloaded and incremental loaded tests; log temperatures, noise,
    efficiency, backlash and wear. Establish acceptable loads/life from test evidence.

The files are prototype references. Static CAD checks do not validate dynamic tooth
contact or commercial service suitability. Gear roots use sampled radial relief.
No validated fatigue, creep, contact wear, housing, retention or thermal rating exists.
"""
        atomic_text(temporary/"ASSEMBLY.txt",assembly_text)
        manifest = {"app_version":__version__,"candidate_id":c.id,"export_level":c.export_level,
                    "cad_included":bool(include_cad and c.export_level != "concept"),"files":{}}
        for file in sorted(temporary.rglob("*")):
            if file.is_file():
                manifest["files"][file.relative_to(temporary).as_posix()] = hashlib.sha256(file.read_bytes()).hexdigest()
        atomic_text(temporary/"manifest.json",json.dumps(manifest,indent=2))
        os.replace(temporary,dest)
        return {"destination":str(dest),"files":len(manifest["files"])+1,"cad_included":manifest["cad_included"]}
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)
