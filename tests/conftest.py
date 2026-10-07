import os

os.environ.setdefault("QT_QPA_PLATFORM","offscreen")
if os.name == "nt":
    os.environ.setdefault("QT_QPA_FONTDIR", os.path.join(os.environ["SystemRoot"], "Fonts"))

import pytest
from gearforge.catalog import Catalog
from gearforge.models import PrintProfile,Requirements


@pytest.fixture
def catalog():
    result=Catalog()
    yield result
    result.close()


@pytest.fixture
def profile():
    return PrintProfile()


@pytest.fixture
def light_requirements():
    return Requirements(input_rpm=400,output_rpm=100,input_torque_nm=.08,output_torque_nm=.12,mode="printed",families=["spur"])
