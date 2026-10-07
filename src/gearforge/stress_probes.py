"""Signed stress at fixed body-frame points, without peak tracking or averaging."""
from dataclasses import dataclass
import csv
import html
import io
import math

import numpy as np

from .engineering import _text
from .models import finite

RESOLVED_COMPONENTS = ('normal_mpa', 'shear_mpa', 'transverse_mpa', 'out_of_plane_mpa')


@dataclass
class StressProbe:
    name: str = 'Material point'
    x_mm: float = 0.
    y_mm: float = 0.
    normal_direction_deg: float = 0.
    basis: str = ''

    def validate(self):
        _text(self.name, 'Probe name', 120, required=True)
        _text(self.basis, 'Material point and direction basis', 4000)
        self.x_mm = finite(self.x_mm, 'Probe X mm', -100000, 100000)
        self.y_mm = finite(self.y_mm, 'Probe Y mm', -100000, 100000)
        self.normal_direction_deg = finite(self.normal_direction_deg, 'Normal direction degrees from +X', -180, 180)


def locate_point(nodes, elements, x_mm, y_mm):
    """Invert each candidate bilinear cell; retain every containing element side.

    Coordinates stay fixed across loads and refinements. A point outside the
    actual polygonal domain is unavailable, never snapped to another location.
    """
    point = np.array([x_mm, y_mm], dtype=float)
    if not np.all(np.isfinite(point)):
        raise ValueError('Probe coordinates must be finite')
    corners = np.asarray(nodes)[np.asarray(elements)[:, :4]]
    scale = max(1., float(np.ptp(corners.reshape(-1, 2), axis=0).max()))
    tolerance = 1e-10 * scale
    candidates = np.flatnonzero(np.all(point >= corners.min(axis=1)-tolerance, axis=1)
                               & np.all(point <= corners.max(axis=1)+tolerance, axis=1))
    locations = []
    for index in candidates:
        cell = corners[index]
        solve_tolerance = 8*np.finfo(float).eps*max(1., float(np.max(abs(cell))))
        natural = np.zeros(2)
        for _ in range(30):
            xi, eta = natural
            weights = np.array([(1-xi)*(1-eta), (1+xi)*(1-eta), (1+xi)*(1+eta), (1-xi)*(1+eta)])/4
            derivatives = np.array([[-(1-eta), -(1-xi)], [(1-eta), -(1+xi)],
                                    [(1+eta), (1+xi)], [-(1+eta), (1-xi)]])/4
            residual = weights @ cell - point
            if np.linalg.norm(residual, ord=np.inf) <= solve_tolerance:
                break
            try:
                natural -= np.linalg.solve(cell.T @ derivatives, residual)
            except np.linalg.LinAlgError:
                break
            if not np.all(np.isfinite(natural)) or np.max(abs(natural)) > 10:
                break
        xi, eta = natural
        if np.max(abs(natural)) > 1+1e-9:
            continue
        xi, eta = np.clip(natural, -1, 1)
        weights = np.array([(1-xi)*(1-eta), (1+xi)*(1-eta), (1+xi)*(1+eta), (1-xi)*(1+eta)])/4
        recovered = weights @ cell
        error = float(np.linalg.norm(recovered-point))
        if error <= 2*tolerance:
            locations.append(dict(element_index=int(index), xi=float(xi), eta=float(eta),
                                  recovered_x_mm=float(recovered[0]), recovered_y_mm=float(recovered[1]),
                                  coordinate_residual_mm=error))
    if not locations:
        raise ValueError('Fixed material point is outside this polygonal mesh; no nearest-point substitution is made')
    return locations


def resolve_stress(stress, direction_deg):
    """[xx, yy, xy, zz] to n.S.n and m.S.n; n fixed in the gear body frame."""
    values = np.asarray(stress, dtype=float)
    if values.shape != (4,) or not np.all(np.isfinite(values)):
        raise ValueError('Four finite stress components are required')
    angle = math.radians(finite(direction_deg, 'Normal direction degrees', -180, 180))
    c, s = math.cos(angle), math.sin(angle)
    xx, yy, xy, zz = values
    return dict(normal_mpa=float(c*c*xx+s*s*yy+2*s*c*xy),
                shear_mpa=float((c*c-s*s)*xy+s*c*(yy-xx)),
                transverse_mpa=float(s*s*xx+c*c*yy-2*s*c*xy), out_of_plane_mpa=float(zz))


def locate_probes(system, probes):
    records = []
    for probe in probes:
        try:
            locations = locate_point(system.nodes, system.elements, probe.x_mm, probe.y_mm)
            records.append(dict(name=probe.name, available=True, locations=locations, finding=None))
        except ValueError as exc:
            records.append(dict(name=probe.name, available=False, locations=[], finding=str(exc)))
    return records


def probe_response(system, displacement, probes, locations):
    records = []
    for probe, location in zip(probes, locations, strict=True):
        values = []
        for side in location['locations']:
            stress = system.stress_at(displacement, [side['element_index']], side['xi'], side['eta'])[0]
            values.append(dict(element_index=side['element_index'], stress_mpa_per_n_mm=stress.tolist(),
                               resolved_mpa_per_n_mm=resolve_stress(stress, probe.normal_direction_deg)))
        records.append(dict(name=probe.name, values=values))
    return records


def probe_changes(first, second, probe_index):
    """Compare component envelopes at one point across every load/flank basis.

    Element IDs change with refinement. Retain all edge-side stresses and compare
    their lower/upper bounds, never averaged values. Normalize by the largest
    signed-component magnitude over this point's complete finer-load trace.
    """
    a, b = [], []
    for earlier, later in zip(first['responses'], second['responses'], strict=True):
        if (earlier['position_fraction'], earlier['flank']) != (later['position_fraction'], later['flank']):
            raise ValueError('Probe comparisons require matching load positions and flanks')
        av = earlier['point_probes'][probe_index]['values']
        bv = later['point_probes'][probe_index]['values']
        if not av or not bv:
            return None
        for source, output in ((av, a), (bv, b)):
            components = np.array([[v['resolved_mpa_per_n_mm'][k] for k in RESOLVED_COMPONENTS] for v in source])
            output.extend((components.min(axis=0), components.max(axis=0)))
    if not b:
        return None
    first_values, second_values = np.array(a), np.array(b)
    scale = float(np.max(abs(second_values)))
    difference = float(np.max(abs(second_values-first_values)))
    return 0. if scale == difference == 0 else 100*difference/max(scale, 1e-30)


def probe_report_html(result):
    probes = result['inputs'].get('probes', [])
    if not probes:
        return ''
    esc = lambda v: html.escape(str(v))
    fmt = lambda v: 'Unassessed' if v is None else f'{v:.7g}'
    verdict = lambda v: 'Unassessed' if v is None else 'Meets entered comparison' if v else 'Unresolved'
    output = ['<h2>Fixed material points</h2><p>Coordinates and directions are fixed in the gear body frame. '
              'Positive normal stress is tension; signed shear acts along the normal rotated +90 degrees. '
              'Each containing element side is retained separately. These are sampled load-position traces, '
              'without chronology, unloaded phases or solved contact sharing; they are not fatigue histories.</p>']
    checks = {c['name']: c for c in result.get('probe_checks', [])}
    for index, probe in enumerate(probes):
        output.append(f"<h3>{esc(probe['name'])}</h3><p>X {fmt(probe['x_mm'])} mm, Y {fmt(probe['y_mm'])} mm; "
                      f"normal {fmt(probe['normal_direction_deg'])} degrees from +X. Basis: {esc(probe['basis']) or 'Missing'}.</p>")
        check = checks.get(probe['name'])
        if check:
            output.append('<p>Mesh changes: '+', '.join(fmt(v) for v in check['mesh_changes_percent'])+'%; '+
                          verdict(check['mesh_convergence_passed'])+'. Wider-sector change: '+
                          fmt(check['domain_change_percent'])+'%; '+verdict(check['domain_sensitivity_passed'])+'.</p>')
        else:
            output.append('<p>Point sensitivity is unassessed.</p>')
        mapping = []
        for level in [*result['mesh_levels'], *([result['domain_check']] if result['domain_check'] else [])]:
            location = level['probe_locations'][index]
            label = f"{level['refinement']}× / {level['sector_teeth']} teeth"
            mapping.append(f"<li>{label}: {len(location['locations'])} containing element side(s)"+
                           ('.' if location['available'] else '; '+esc(location['finding']))+'</li>')
        output.append('<ul>'+''.join(mapping)+'</ul>')
        rows = []
        for case in result['cases']:
            for position in case['positions']:
                values = position['point_probes'][index]['values']
                prefix = f"<td>{esc(case['name'])}</td><td>{fmt(position['position_fraction'])}</td><td>{esc(case['flank'])}</td>"
                if not values:
                    rows.append('<tr>'+prefix+'<td colspan="5">Outside fine mesh; no substituted stress</td></tr>')
                for value in values:
                    rows.append('<tr>'+prefix+f"<td>{value['element_index']}</td>"+
                                ''.join('<td>'+fmt(value['resolved_mpa'][key])+'</td>' for key in RESOLVED_COMPONENTS)+'</tr>')
        if rows:
            output.append('<table><tr><th>Case</th><th>Path fraction</th><th>Flank</th><th>Element (0-based)</th>'
                          '<th>Normal MPa</th><th>Shear MPa</th><th>Transverse MPa</th><th>Out of plane MPa</th></tr>'+''.join(rows)+'</table>')
        else:
            output.append('<p>No assessed operating-case point stress.</p>')
    return ''.join(output)


def probe_csv(result):
    """Actual signed stresses; unavailable cases/points remain explicit blank rows."""
    stream = io.StringIO(newline='')
    writer = csv.writer(stream)
    writer.writerow(['case', 'path_fraction', 'flank', 'point', 'x_mm', 'y_mm', 'normal_direction_deg',
                     'status', 'element_index', 'sigma_x_mpa', 'sigma_y_mpa', 'tau_xy_mpa', 'sigma_z_mpa',
                     *RESOLVED_COMPONENTS])
    def safe(value):
        return "'"+value if value.lstrip().startswith(('=', '+', '-', '@')) or value.startswith(('\t', '\r', '\n')) else value
    for case in result['cases']:
        for index, probe in enumerate(result['inputs'].get('probes', [])):
            for position in case['positions'] or [None]:
                prefix = [safe(case['name']), position['position_fraction'] if position else '', case['flank'],
                          safe(probe['name']), probe['x_mm'], probe['y_mm'], probe['normal_direction_deg']]
                if position is None:
                    writer.writerow([*prefix, 'Operating case unassessed', *(['']*9)])
                    continue
                values = position['point_probes'][index]['values']
                if not values:
                    writer.writerow([*prefix, 'Outside fine mesh', *(['']*9)])
                for value in values:
                    writer.writerow([*prefix, 'Available', value['element_index'], *value['stress_mpa'],
                                     *[value['resolved_mpa'][key] for key in RESOLVED_COMPONENTS]])
    return stream.getvalue()
