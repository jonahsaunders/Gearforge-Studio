import json
import os
from pathlib import Path
import subprocess
import sys
from dataclasses import asdict

from gearforge.models import Project

ROOT=Path(__file__).resolve().parents[1]


def test_release_tag_guard():
    process=subprocess.run([sys.executable,str(ROOT/'scripts/check_version.py')],env=dict(os.environ,GITHUB_REF='refs/tags/v9.9.9'),capture_output=True,text=True)
    assert process.returncode!=0 and 'match package version' in process.stderr


def test_windowed_file_worker_without_stdin(tmp_path,catalog):
    project=Project();output=tmp_path/'result.json';request=tmp_path/'request.json'
    request.write_text(json.dumps(dict(task='search',result_path=str(output),requirements=asdict(project.requirements),profile=asdict(project.profile),catalog_text=catalog.export_csv(),limit=1)))
    process=subprocess.run([sys.executable,'-m','gearforge.cli','--worker-file',str(request)],stdin=subprocess.DEVNULL,capture_output=True,text=True,timeout=30)
    assert process.returncode==0,process.stderr
    assert json.loads(output.read_text())['ok']
