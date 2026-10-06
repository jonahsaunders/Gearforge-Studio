import json
import math
from dataclasses import asdict
from pathlib import Path

import pytest

from gearforge.cli import main
from gearforge.engine import external_contact_ratio
from gearforge.engineering import EngineeringStudy, GearPair, DutyPoint, calculate_study, pair_geometry, export_study, study_html, study_for_stage
from gearforge.maintenance import verify_bundle
from gearforge.models import GearSpec


def test_independent_open_source_geometry_reference():
    fixture = json.loads((Path(__file__).parent / "data/open_geometry_reference.json").read_text(encoding="utf-8"))
    assert fixture["reference_commit"] == "83ec154b1925347622b61812f75d2ed51e956b9f"
    assert len(fixture["cases"]) == 6
    for case in fixture["cases"]:
        actual = pair_geometry(GearPair(**case["pair"]))
        for key, expected in case["expected"].items():
            value = actual
            for part in key.split("."):value = value[part]
            assert value == pytest.approx(expected, rel=2e-7, abs=1e-7), (case["name"], key)


def test_agreed_reference_target_energy_force_and_exposure():
    result = calculate_study(EngineeringStudy())
    row = result["duty_results"][0]
    # Independent hand calculations: P=T*omega; Ft=T/r; revolutions=rpm*60*h.
    assert row["input_power_w"] == pytest.approx(250)
    assert row["output_rpm"] == -300
    assert row["tangential_force_n"] == pytest.approx(79.57747154594767)
    assert row["radial_force_magnitude_n"] == pytest.approx(28.9638309608906)
    assert row["axial_force_n"] == 0
    assert row["estimated_loss_power_w"] == pytest.approx(12.5)
    assert row["input_power_w"] == pytest.approx(row["estimated_output_power_w"] + row["estimated_loss_power_w"])
    assert result["total_pinion_revolutions"] == 900_000_000
    assert result["total_wheel_revolutions"] == 180_000_000
    assert result["total_estimated_loss_energy_kwh"] == pytest.approx(125)
    assert result["geometry"]["operating_center_distance_mm"] == pytest.approx(120)
    assert not result["production_approved"]
    assert result["rated_output_torque_nm"] is result["rated_life_hours"] is None


def test_helical_force_uses_transverse_pressure_angle():
    # Define an independently simple transverse geometry: mt=2 mm, alpha_t=20°.
    beta = math.radians(21.5)
    pair = GearPair(normal_module_mm=2 * math.cos(beta), pinion_teeth=20, wheel_teeth=40,
                    normal_pressure_angle_deg=math.degrees(math.atan(math.tan(math.radians(20)) * math.cos(beta))),
                    pinion_helix_angle_deg=21.5)
    result = calculate_study(EngineeringStudy(pair=pair, duty=[DutyPoint(input_torque_nm=2)]))
    row = result["duty_results"][0]
    assert result["geometry"]["pinion"]["reference_diameter_mm"] == pytest.approx(40)
    assert row["tangential_force_n"] == pytest.approx(100)
    assert row["radial_force_magnitude_n"] == pytest.approx(36.39702342662024)
    assert row["axial_force_n"] == pytest.approx(39.3910475793)
    assert row["ideal_output_torque_magnitude_nm"] == pytest.approx(4)


def test_existing_search_uses_same_normal_system_geometry():
    pair = GearPair(normal_module_mm=2, pinion_teeth=20, wheel_teeth=60, pinion_helix_angle_deg=30, face_width_mm=18)
    expected = pair_geometry(pair)
    pinion, wheel = GearSpec(20, 2, 18, 8, helix_deg=30), GearSpec(60, 2, 18, 10, helix_deg=-30)
    assert external_contact_ratio(pinion, wheel) == pytest.approx(expected["total_contact_ratio"])
    assert expected["transverse_pressure_angle_deg"] == pytest.approx(22.795877258858475)


def test_selected_design_stage_preserves_required_load(catalog, profile, light_requirements):
    from gearforge.engine import synthesize
    candidate = synthesize(light_requirements, profile, catalog, limit=1).candidates[0]
    study = study_for_stage(candidate, light_requirements)
    assert study.pair.pinion_teeth == candidate.stages[0].driver.teeth
    assert study.duty[0].input_torque_nm == candidate.stages[0].input_torque_nm
    assert study.duty[0].input_torque_nm != light_requirements.input_torque_nm
    assert study.target_life_hours == light_requirements.life_hours
    assert candidate.id in study.notes
    with pytest.raises(ValueError):study_for_stage(candidate, light_requirements, 99)
    candidate.family = "planetary"
    with pytest.raises(ValueError, match="spur/helical"):study_for_stage(candidate, light_requirements)


def test_duty_reverse_rest_and_starts_are_not_invented_life_ratings():
    study = EngineeringStudy(pair=GearPair(pinion_helix_angle_deg=20), duty=[
        DutyPoint(name="Forward", input_rpm=1500, input_torque_nm=2, duration_hours=6000, starts=20),
        DutyPoint(name="Reverse", input_rpm=-750, input_torque_nm=-3, duration_hours=3000, starts=15),
        DutyPoint(name="Stationary", input_rpm=0, input_torque_nm=4, duration_hours=1000),
    ])
    result = calculate_study(study)
    forward, reverse, rest = result["duty_results"]
    assert forward["axial_force_n"] > 0 > reverse["axial_force_n"]
    assert reverse["radial_force_magnitude_n"] > 0
    assert reverse["output_rpm"] == 150
    assert rest["pinion_revolutions"] == rest["input_power_w"] == rest["estimated_loss_power_w"] == 0
    assert rest["estimated_output_torque_magnitude_nm"] is None
    assert rest["tangential_force_n"] > 0
    assert result["total_pinion_revolutions"] == 675_000_000
    assert sum(p["starts"] for p in result["duty_results"]) == 35
    assert result["rated_life_hours"] is None


@pytest.mark.parametrize("change", [
    {"duration_hours": 9999}, {"input_rpm": float("nan")}, {"input_torque_nm": True},
    {"input_rpm": 100, "input_torque_nm": -2}, {"ambient_c": 41}, {"starts": 1.5},
])
def test_invalid_duty_is_rejected(change):
    study = EngineeringStudy()
    for name, value in change.items():setattr(study.duty[0], name, value)
    with pytest.raises(ValueError):calculate_study(study)


@pytest.mark.parametrize("change", [{"pinion_teeth": True}, {"pinion_teeth": 20.5},
                                    {"pinion_helix_angle_deg": 90}, {"normal_module_mm": 0},
                                    {"pinion_profile_shift": -1, "wheel_profile_shift": -1, "pinion_teeth": 6, "wheel_teeth": 6}])
def test_invalid_geometry_is_rejected(change):
    with pytest.raises(ValueError):pair_geometry(GearPair(**change))


def test_undercut_screen_is_explicit_and_not_an_approval():
    study = EngineeringStudy(pair=GearPair(pinion_teeth=12, wheel_teeth=24))
    result = calculate_study(study)
    assert any("undercut" in issue for issue in result["geometry"]["issues"])
    assert not result["production_approved"]


def test_study_roundtrip_fingerprint_and_escaped_report(tmp_path):
    study = EngineeringStudy(name="Company <script>alert(1)</script> & 齿轮")
    path = tmp_path / "study.gearforge-study"
    study.save(path)
    loaded = EngineeringStudy.load(path)
    assert asdict(loaded) == asdict(study)
    original = calculate_study(study)
    assert calculate_study(loaded)["study_sha256"] == original["study_sha256"]
    loaded.duty[0].input_torque_nm *= 2
    assert calculate_study(loaded)["study_sha256"] != original["study_sha256"]
    assert "<script>" not in study_html(original)
    assert "&lt;script&gt;" in study_html(original)
    study.evidence_references = "approved in a note"
    assert not calculate_study(study)["production_approved"]


@pytest.mark.parametrize("change", [{"unknown": 1}, {"schema_version": True}, {"pair": []},
                                    {"duty": None}, {"duty": [{"unknown": 2}]}, {"duty": []}])
def test_study_rejects_unknown_or_malformed_fields(change):
    data = asdict(EngineeringStudy()); data.update(change)
    with pytest.raises((ValueError, TypeError)):EngineeringStudy.from_dict(data)


@pytest.mark.parametrize("section,key", [(None, "assumed_efficiency"), ("pair", "normal_module_mm"), ("duty", "input_torque_nm")])
def test_study_never_silently_defaults_missing_saved_inputs(section, key):
    data = asdict(EngineeringStudy())
    target = data if section is None else data["duty"][0] if section == "duty" else data[section]
    del target[key]
    with pytest.raises(ValueError, match="Missing"):EngineeringStudy.from_dict(data)


def test_cli_study_export_and_integrity(tmp_path):
    path = tmp_path / "study.gearforge-study"; output = tmp_path / "calculation"
    assert main(["study", "new", str(path)]) == 0
    assert main(["study", "new", str(path)]) == 1
    assert main(["study", "calculate", str(path), "--out", str(output)]) == 0
    manifest = verify_bundle(output)
    assert manifest["kind"] == "gearforge-engineering-study"
    result = json.loads((output / "calculation.json").read_text(encoding="utf-8"))
    assert manifest["study_sha256"] == result["study_sha256"]
    assert result["inputs"] == asdict(EngineeringStudy.load(output / "design.gearforge-study"))
    assert main(["study", "calculate", str(path), "--out", str(output)]) == 1
    (output / "report.html").write_text("tampered", encoding="utf-8")
    with pytest.raises(ValueError, match="integrity"):verify_bundle(output)


def test_invalid_study_does_not_publish_or_replace(tmp_path):
    study = EngineeringStudy(); path = tmp_path / "original.gearforge-study"
    study.save(path); before = path.read_bytes()
    study.target_life_hours = 20
    with pytest.raises(ValueError):study.save(path)
    assert path.read_bytes() == before
    with pytest.raises(ValueError):export_study(study, tmp_path / "must-not-exist")
    assert not (tmp_path / "must-not-exist").exists()


@pytest.mark.gui
def test_engineering_editor_calculation_invalidation_and_failed_save(tmp_path, monkeypatch):
    from PySide6.QtWidgets import QApplication, QFileDialog
    from gearforge.engineering_ui import EngineeringStudyDialog
    app = QApplication.instance() or QApplication([])
    dialog = EngineeringStudyDialog(); errors = []; dialog.show_error = lambda error: errors.append(str(error))
    dialog.show(); app.processEvents()
    assert dialog.calculate()
    assert dialog.result["duty_results"][0]["input_power_w"] == pytest.approx(250)
    assert not dialog.report.grab().isNull()
    dialog.pair_fields["pinion_helix_angle_deg"].setValue(20)
    assert dialog.result is None and not dialog.report.toPlainText() and dialog.dirty
    assert dialog.calculate() and dialog.result["duty_results"][0]["axial_force_n"] > 0
    original = tmp_path / "original.gearforge-study"; dialog.path = original
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a: (str(tmp_path / "new.gearforge-study"), ""))
    def fail_save(*args):raise OSError("Disk full")
    monkeypatch.setattr(EngineeringStudy, "save", fail_save)
    assert not dialog.save_study() and dialog.path == original and dialog.dirty
    assert errors == ["Disk full"]
    dialog.dirty = False; dialog.close(); app.processEvents()
