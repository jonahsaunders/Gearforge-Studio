import json
from pathlib import Path
import sys

import numpy as np

from gearforge.elastic_contact import solve_contact_loads

ROOT=Path(__file__).resolve().parents[1]


def test_separate_scikit_fem_closed_ring_and_scipy_contact_references():
    sys.path.insert(0,str(ROOT/'scripts'))
    from verify_loaded_mesh_reference import ring_application
    fixture=json.loads((ROOT/'tests/data/open_loaded_mesh_reference.json').read_text());count=0
    assert fixture['reference_license']=='BSD-3-Clause' and fixture['elastic_reference_version']=='12.0.2'
    for case in fixture['rings']:
        actual,_=ring_application(case);expected=case['expected']
        assert actual['nodes']==expected['nodes'] and actual['elements']==expected['elements']
        for key,absolute in [('compliance',2e-11),('point_stress',2e-9),('strain_energy',2e-11)]:
            np.testing.assert_allclose(actual[key],expected[key],rtol=2e-8,atol=absolute)
    for case in fixture['contacts']:
        actual=solve_contact_loads(case['compliance'],case['gaps'],case['arms'],case['torque'])
        for key,actual_key in [('forces','normal_forces_n'),('rotation','relative_rotation_rad'),('residual','contact_residual_mm'),('energy','strain_energy_n_mm')]:
            np.testing.assert_allclose(actual[actual_key],case['expected'][key],rtol=2e-8,atol=2e-9)
            count+=np.asarray(actual[actual_key]).size
    assert count==fixture['contact_comparisons']==1760
