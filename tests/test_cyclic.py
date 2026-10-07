from dataclasses import asdict
import copy
import json
from pathlib import Path
import time

import pytest

from gearforge.cyclic import (HistoryStudy, HistoryBlock, StressSample, SNPoint, count_history,
    synthetic_history_example, calculate_history_study, parse_sample_csv, import_sample_csv,
    sn_failure_cycles, history_from_study, export_history_study, history_report_html, history_csv_files)
from gearforge.maintenance import verify_bundle


def test_finite_half_cycles_plateaus_nested_ranges_and_boundary_closures():
    assert count_history([([0, 100], 1)])['cycles'][0]['count'] == .5
    assert count_history([([10, 10, 10], 10**12)])['cycles'] == []
    small = count_history([([0, 100, 20, 80, 0, -60, 0], 1)])
    assert [(c['minimum_stress_mpa'], c['maximum_stress_mpa'], c['count']) for c in small['cycles']] == [(-60, 0, .5), (-60, 100, .5), (0, 100, .5), (20, 80, 1)]
    segmented = count_history([([0, 100, 20], 1), ([20, 80, 0, -60, 0], 1)])
    assert small['cycles'] == segmented['cycles']
    # Closing blocks separately loses the cross-boundary 20-to-80 full cycle.
    assert sum(c['count'] for c in small['cycles']) == 2.5


def test_repeated_block_keeps_finite_endpoints_and_runs_in_bounded_space():
    started = time.monotonic()
    result = count_history([([0, 1, 0], 10**12)])
    assert result['cycles'][0]['half_cycles'] == 2*10**12
    assert result['expanded_samples'] == 2*10**12+1
    assert result['blocks'][0]['processed_repetitions'] <= 3
    assert time.monotonic()-started < 2
    s = synthetic_history_example()
    r = calculate_history_study(s)
    assert r['damage'] == pytest.approx(.16310411314380596, rel=1e-12)
    assert r['coverage_complete'] and r['fatigue_damage_available']
    assert r['counting']['expanded_samples'] == 5_400_000_001
    assert r['counting']['total_half_cycles'] == 3_600_000_001
    assert not r['production_approved'] and not r['declared_input_evidence_complete']
    assert r['rated_output_torque_nm'] is None and r['rated_gearbox_life_hours'] is None


def test_saved_independent_reference():
    fixture = json.loads((Path(__file__).parent/'data/open_history_reference.json').read_text())
    assert fixture['passed'] and fixture['reference_version'] == '3.2.0'
    for case in fixture['cases']:
        result = count_history([(list(v), n) for v, n in case['blocks']])
        assert [{k: c[k] for k in ('minimum_stress_mpa', 'maximum_stress_mpa', 'half_cycles')} for c in result['cycles']] == case['expected_cycles']
    for case in fixture['arithmetic']:
        s = synthetic_history_example()
        s.stress_design_factor = case['stress_design_factor']
        r = calculate_history_study(s)
        assert r['damage'] == pytest.approx(case['expected_damage'], rel=1e-11)
        for actual, expected in zip(r['cycles'], case['expected_cycles'], strict=True):
            for key, value in expected.items():
                assert actual[key] == pytest.approx(value, rel=1e-11)


@pytest.mark.parametrize('change', [
    lambda s: setattr(s, 'stress_state', 'other'),
    lambda s: setattr(s, 'mean_stress_model', 'unverified'),
    lambda s: setattr(s.material, 'ultimate_tensile_mpa', None),
    lambda s: setattr(s.material, 'elastic_limit_mpa', None),
    lambda s: setattr(s.material, 'elastic_limit_mpa', 99),
    lambda s: setattr(s, 'history_minimum_temperature_c', None),
    lambda s: setattr(s, 'history_maximum_temperature_c', 81),
    lambda s: setattr(s.material, 'sn_curve', []),
])
def test_unsupported_conditions_keep_counts_but_no_damage(change):
    s = synthetic_history_example()
    change(s)
    r = calculate_history_study(s)
    assert r['calculation_available'] and r['cycles']
    assert not r['fatigue_damage_available'] and r['damage'] is None and r['known_damage_lower_bound'] is None
    assert not r['production_approved']


def test_unknown_is_not_zero_and_partial_coverage_is_not_full_duty():
    r = calculate_history_study(HistoryStudy())
    assert not r['calculation_available'] and r['damage'] is None
    s = synthetic_history_example()
    s.blocks[0].repetitions //= 2
    r = calculate_history_study(s)
    assert r['fatigue_damage_available'] and not r['coverage_complete']
    assert not r['declared_input_evidence_complete']
    s.blocks[0].samples = []
    assert not calculate_history_study(s)['calculation_available']


def test_sn_endpoints_interpolation_no_infinite_life_or_extrapolation():
    curve = [SNPoint(1000, 100), SNPoint(100000, 10)]
    assert sn_failure_cycles(curve, 100) == 1000
    assert sn_failure_cycles(curve, 10) == 100000
    assert sn_failure_cycles(curve, 10**1.5) == pytest.approx(10000)
    assert sn_failure_cycles(curve, 9.999) is None and sn_failure_cycles(curve, 100.001) is None
    s = synthetic_history_example()
    s.material.sn_curve[-1].amplitude_mpa = 40
    r = calculate_history_study(s)
    assert r['damage'] is None and r['known_damage_lower_bound'] > 0
    assert r['entered_limit_assessment'] == 'unavailable'
    s.damage_limit = .000001
    assert calculate_history_study(s)['entered_limit_assessment'] == 'known_lower_bound_exceeds_entered_limit'


def test_mean_stress_no_compressive_credit_and_full_reversal_scope():
    s = synthetic_history_example()
    r = calculate_history_study(s)
    c = r['cycles'][0]
    assert c['design_mean_mpa'] < 0 and c['equivalent_fully_reversed_amplitude_mpa'] == c['design_amplitude_mpa']
    s.mean_stress_model = 'fully_reversed_only'
    r = calculate_history_study(s)
    assert r['damage'] is None and r['known_damage_lower_bound'] == 0
    s.blocks[0].samples = [StressSample(0, -100), StressSample(.02, 100), StressSample(.04, -100)]
    r = calculate_history_study(s)
    assert r['fatigue_damage_available'] and len(r['cycles']) == 1
    s.blocks[0].samples = [StressSample(0, 50), StressSample(.04, 50)]
    r = calculate_history_study(s)
    assert r['fatigue_damage_available'] and r['damage'] == 0 and not r['production_approved']


def test_declared_input_status_is_separate_from_limits_and_approval():
    s = synthetic_history_example()
    s.material.data_status = 'declared'
    s.blocks[0].data_status = 'declared'
    r = calculate_history_study(s)
    assert r['declared_input_evidence_complete'] and not r['production_approved']
    s.damage_limit = .001
    r = calculate_history_study(s)
    assert r['declared_input_evidence_complete'] and r['entered_limit_assessment'] == 'exceeds_entered_limit'
    for path in ('point_definition', 'coverage_basis', 'mean_stress_basis', 'stress_factor_basis'):
        trial = copy.deepcopy(s)
        setattr(trial, path, '')
        assert not calculate_history_study(trial)['declared_input_evidence_complete']
    s.blocks[0].starts_per_repeat = None
    assert not calculate_history_study(s)['coverage_complete']


@pytest.mark.parametrize('change', [
    lambda s: setattr(s, 'schema_version', True),
    lambda s: setattr(s, 'stress_design_factor', float('nan')),
    lambda s: setattr(s.blocks[0], 'repetitions', 1.5),
    lambda s: setattr(s.blocks[0], 'repetitions', 10**15),
    lambda s: setattr(s.blocks[0], 'starts_per_repeat', True),
    lambda s: setattr(s.blocks[0].samples[0], 'time_s', .01),
    lambda s: setattr(s.blocks[0].samples[1], 'time_s', 0),
    lambda s: setattr(s.blocks[0].samples[1], 'stress_mpa', float('inf')),
    lambda s: setattr(s.blocks[0].samples[-1], 'stress_mpa', 1),
    lambda s: setattr(s.blocks[0], 'samples', [StressSample()]),
    lambda s: setattr(s.blocks[0], 'duty_case_name', 'missing'),
    lambda s: setattr(s.material.sn_curve[1], 'amplitude_mpa', 250),
    lambda s: setattr(s.material, 'survival_probability', 1),
    lambda s: setattr(s.material, 'elastic_limit_mpa', 700),
    lambda s: setattr(s.blocks[0], 'imported_file_sha256', 'x'),
])
def test_strict_validation(change):
    s = synthetic_history_example()
    change(s)
    with pytest.raises(ValueError):
        s.validate()


def test_seams_sample_budget_and_source_copy():
    with pytest.raises(ValueError, match='endpoint'):
        count_history([([0, 1], 1), ([2, 3], 1)])
    with pytest.raises(ValueError, match='starting stress'):
        count_history([([0, 1], 2)])
    with pytest.raises(ValueError, match='expanded'):
        count_history([([0]*1001, 10**12)])
    source = synthetic_history_example().source
    new = history_from_study(source)
    new.source.name = 'Changed'
    assert source.name != new.source.name
    assert not new.blocks[0].samples and new.material.elastic_limit_mpa is None


def test_csv_import_fingerprints_edit_detection_and_atomic_failure(tmp_path):
    path = tmp_path/'history.csv'
    path.write_text('\ufefftime_s,stress_mpa\n0,0\n0.02,100\n0.04,0\n', encoding='utf-8')
    s = synthetic_history_example()
    import_sample_csv(path, s.blocks[0])
    assert calculate_history_study(s)['block_provenance'][0]['imported_samples_unchanged'] is True
    s.blocks[0].samples[1].stress_mpa = 101
    assert calculate_history_study(s)['block_provenance'][0]['imported_samples_unchanged'] is False
    saved = asdict(s.blocks[0])
    path.write_text('time_s,stress_mpa\n0,nan\n1,0\n')
    with pytest.raises(ValueError):
        import_sample_csv(path, s.blocks[0])
    assert asdict(s.blocks[0]) == saved
    for text in ('time,stress\n0,1\n1,2', 'time_s,stress_mpa\n0,1,2\n1,2', 'time_s,stress_mpa\n0,1', 'time_s,stress_mpa\n1,0\n2,1'):
        with pytest.raises(ValueError):
            parse_sample_csv(text)


def test_roundtrip_strict_json_safe_exports_and_no_overwrite(tmp_path):
    s = synthetic_history_example()
    s.name = '<script>unsafe</script>'
    s.blocks[0].name = '=malicious()'
    path = tmp_path/'sample.gearforge-history'
    s.save(path)
    assert asdict(HistoryStudy.load(path)) == asdict(s)
    unknown = asdict(s)
    unknown['production_approved'] = True
    with pytest.raises(ValueError):
        HistoryStudy.from_dict(unknown)
    for content in ('{"name":0,"name":1}', '{"name":NaN}'):
        path.write_text(content)
        with pytest.raises(ValueError):
            HistoryStudy.load(path)
    r = calculate_history_study(s)
    assert '<script>' not in history_report_html(r) and '&lt;script&gt;' in history_report_html(r)
    assert "'=malicious()" in history_csv_files(r)['history-samples.csv']
    out = tmp_path/'assessment'
    result = export_history_study(s, out)
    assert result['files'] == 6 and len(verify_bundle(out)['files']) == 5
    with pytest.raises(ValueError):
        export_history_study(s, out)


def test_cli_history_import_worker_and_no_overwrite(tmp_path, capsys):
    from gearforge.cli import main
    path = tmp_path/'example.gearforge-history'
    assert main(['history', 'new', str(path), '--synthetic-example']) == 0
    assert main(['history', 'new', str(path)]) == 1
    csv_path = tmp_path/'samples.csv'
    csv_path.write_text('time_s,stress_mpa\n0,0\n0.01,100\n0.04,0\n')
    imported = tmp_path/'imported.gearforge-history'
    assert main(['history', 'import-csv', str(path), str(csv_path), '--block', 'Invented repeated waveform', '--out', str(imported)]) == 0
    assert HistoryStudy.load(imported).blocks[0].imported_file_sha256
    out = tmp_path/'export'
    assert main(['history', 'calculate', str(imported), '--out', str(out)]) == 0
    assert len(verify_bundle(out)['files']) == 5
    request = tmp_path/'request.json'
    response = tmp_path/'result.json'
    request.write_text(json.dumps(dict(task='history-calculate', result_path=str(response), study=asdict(HistoryStudy.load(path)))))
    assert main(['--worker-file', str(request)]) == 0
    assert json.loads(response.read_text())['result']['fatigue_damage_available']
    assert main(['history', 'calculate', str(imported), '--out', str(out)]) == 1


def test_history_math_imports_without_site_packages():
    import subprocess
    import sys
    source = str(Path(__file__).resolve().parents[1]/'src')
    code = 'import sys; sys.path.insert(0,'+repr(source)+'); from gearforge.cyclic import synthetic_history_example, calculate_history_study; assert calculate_history_study(synthetic_history_example())["fatigue_damage_available"]'
    result = subprocess.run([sys.executable, '-S', '-c', code], capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stderr


@pytest.mark.gui
def test_history_editor_preserves_invalid_buffers_order_hashes_and_save_failure(tmp_path, monkeypatch):
    from PySide6.QtWidgets import QApplication, QFileDialog
    from gearforge.cyclic_ui import HistoryStudyDialog
    app = QApplication.instance() or QApplication([])
    study = synthetic_history_example()
    dialog = HistoryStudyDialog(study=study)
    errors = []
    dialog.show_error = lambda error: errors.append(str(error))
    dialog.show()
    app.processEvents()
    assert asdict(dialog.read_study()) == asdict(study)
    assert dialog.tabs.count() == 7
    # Switching blocks retains an invalid in-progress edit without accepting it.
    dialog.samples.setPlainText('invalid CSV being edited')
    dialog.add_block()
    dialog.samples.setPlainText('time_s,stress_mpa\n0,0\n1,0\n')
    dialog.fingerprints[1] = ('a'*64, 'b'*64)
    dialog.move_block(-1)
    assert dialog.sample_texts[1] == 'invalid CSV being edited'
    assert dialog.fingerprints[0] == ('a'*64, 'b'*64)
    dialog.table.setCurrentCell(1, 0)
    assert dialog.samples.toPlainText() == 'invalid CSV being edited'
    assert not dialog.calculate() and errors
    dialog.remove_block()
    assert dialog.read_study().blocks[0].imported_file_sha256 == 'a'*64
    dialog.set_study(study)
    dialog.basis_fields['point_definition'].setText('Edited point')
    old = tmp_path/'old.gearforge-history'
    dialog.path = old
    monkeypatch.setattr(QFileDialog, 'getSaveFileName', lambda *a: (str(tmp_path/'new.gearforge-history'), ''))
    def fail(*args):
        raise OSError('Disk full')
    monkeypatch.setattr(HistoryStudy, 'save', fail)
    assert not dialog.save_study() and dialog.dirty and dialog.path == old and errors[-1] == 'Disk full'
    dialog.dirty = False
    dialog.close()
    app.processEvents()


@pytest.mark.gui
def test_history_desktop_worker_plots_export_and_cancellation(tmp_path):
    from PySide6.QtWidgets import QApplication
    from gearforge.cyclic_ui import HistoryStudyDialog
    app = QApplication.instance() or QApplication([])
    dialog = HistoryStudyDialog(study=synthetic_history_example())
    errors = []
    dialog.show_error = lambda error: errors.append(str(error))
    dialog.show()
    def wait():
        deadline = time.monotonic()+30
        while dialog.process is not None and time.monotonic() < deadline:
            app.processEvents()
            time.sleep(.01)
        assert dialog.process is None and not errors
    assert dialog.calculate() and dialog.cancel.isEnabled()
    wait()
    assert dialog.result['damage'] == pytest.approx(.16310411314380596)
    for index in range(7):
        dialog.tabs.setCurrentIndex(index)
        app.processEvents()
        assert not dialog.grab().isNull()
    dialog.tabs.setCurrentIndex(4)
    for index in range(3):
        dialog.plot_mode.setCurrentIndex(index)
        app.processEvents()
        assert dialog.plot.rendered_items > 0
    out = tmp_path/'worker-export'
    assert dialog.start_job('history-export', dialog.read_study(), out)
    wait()
    assert len(verify_bundle(out)['files']) == 5
    dialog.material_fields['elastic_limit_mpa'].setText('99')
    assert dialog.dirty and dialog.result is None
    assert dialog.calculate()
    wait()
    assert not dialog.result['fatigue_damage_available']
    assert dialog.calculate()
    dialog.cancel_job()
    assert dialog.process is None and dialog.worker.temporary is None and dialog.result is None
    dialog.dirty = False
    dialog.close()
    app.processEvents()
