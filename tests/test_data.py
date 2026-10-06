import csv
import io
import json
from dataclasses import asdict

import pytest
from gearforge.calibration import calibrate_profile
from gearforge.catalog import Catalog,CSV_COLUMNS
from gearforge.exporting import safe_cell,report_html
from gearforge.models import Project,Requirements,PrintProfile


def test_project_roundtrip(tmp_path):
    p=Project(name="Motor <A>",notes="Assembly notes")
    path=tmp_path/"project.gearforge";p.save(path)
    assert asdict(Project.load(path))==asdict(p)


@pytest.mark.parametrize("payload",[{"schema_version":99},{"schema_version":1,"requirements":{},"profile":{},"exec":"bad"}])
def test_unknown_project_schema(tmp_path,payload):
    path=tmp_path/"project.gearforge";path.write_text(json.dumps(payload))
    with pytest.raises(ValueError):Project.load(path)


def test_json_nonfinite_rejected(tmp_path):
    path=tmp_path/"p.gearforge";path.write_text('{"schema_version":1,"requirements":{"input_rpm":NaN},"profile":{}}')
    with pytest.raises(ValueError):Project.load(path)


def test_catalog_import_atomic(catalog):
    original=catalog.export_csv()
    rows=list(csv.DictReader(io.StringIO(original)))
    rows[0]["sku"]="NEW-PART";rows[-1]["module_mm"]="nan"
    output=io.StringIO();writer=csv.DictWriter(output,fieldnames=CSV_COLUMNS);writer.writeheader();writer.writerows(rows)
    with pytest.raises(ValueError):catalog.import_csv(output.getvalue())
    assert catalog.export_csv()==original


def test_catalog_roundtrip_and_profile_storage(catalog,profile):
    text=catalog.export_csv();assert catalog.import_csv(text)==len(catalog.rows())
    catalog.save_profile(profile)
    assert asdict(catalog.profiles()[0])==asdict(profile)


def test_catalog_formula_payload_rejected(catalog):
    text=catalog.export_csv().replace("SS1-20", "=BAD()",1)
    with pytest.raises(ValueError,match="formula"):catalog.import_csv(text)


def test_dimensional_calibration_does_not_infer_strength(profile):
    p=calibrate_profile(profile,39.6,40,9.7,10,"test 001")
    assert p.shrink_percent==pytest.approx(1)
    assert p.bore_compensation_mm==pytest.approx(.2)
    assert p.allowable_mpa==profile.allowable_mpa
    assert "test 001" in p.test_evidence


def test_csv_formula_injection():
    assert safe_cell("=HYPERLINK('bad')").startswith("'")
    assert safe_cell("  +cmd").startswith("'")
    assert safe_cell(-1)==-1


@pytest.mark.parametrize("patch",[
    {"schema_version": True}, {"requirements": None}, {"profile": []},
    {"requirements": {"unknown": 4}}, {"selected_id": []}, {"design_snapshot": []},
    {"name": "x" * 201}, {"notes": "x" * 20001},
])
def test_project_rejects_malformed_structure(tmp_path,patch):
    data=asdict(Project());data.update(patch)
    path=tmp_path/"bad.gearforge";path.write_text(json.dumps(data),encoding="utf-8")
    with pytest.raises(ValueError):Project.load(path)


@pytest.mark.parametrize("text",[
    '{"schema_version":1}',
    '{"schema_version":1,"schema_version":1,"requirements":{},"profile":{}}',
    '{"schema_version":1,"requirements":{},"profile":{},"design_snapshot":{"value":1e999}}',
    '['*2000+'0'+']'*2000,
])
def test_project_rejects_ambiguous_or_incomplete_json(tmp_path,text):
    path=tmp_path/"bad.gearforge";path.write_text(text,encoding="utf-8")
    with pytest.raises(ValueError):Project.load(path)


def test_invalid_save_preserves_existing_project(tmp_path):
    path=tmp_path/"project.gearforge";Project(name="Original").save(path)
    with pytest.raises(ValueError):Project(name="x"*201).save(path)
    assert Project.load(path).name=="Original"


@pytest.mark.parametrize("url",["https://", "https://user:secret@example.com", "https://example.com/\npath", "file:///etc/passwd"])
def test_catalog_rejects_invalid_source_links(catalog,url):
    rows=list(csv.DictReader(io.StringIO(catalog.export_csv())))
    rows[0]["source_url"]=url
    stream=io.StringIO();writer=csv.DictWriter(stream,fieldnames=CSV_COLUMNS)
    writer.writeheader();writer.writerows(rows)
    with pytest.raises(ValueError):catalog.import_csv(stream.getvalue())
