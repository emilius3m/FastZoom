from datetime import datetime

import pytest
from pydantic import ValidationError

from app.schemas.tma import SchedaTMACreate


def base_payload():
    return {
        "tsk": "SHOULD_BE_IGNORED",
        "lir": "C",
        "nctr": "12",
        "nctn": "123",
        "esc": "S19",
        "ecp": "R08",
        "ogtd": "materiale proveniente da Unità Stratigrafica",
        "ogtm": "ceramica / vetro",
        "pvcs": "ITALIA",
        "pvcr": "Lazio",
        "pvcp": "RM",
        "pvcc": "Roma",
        "dtzg": "età romana",
        "dtm": ["analisi tipologica"],
        "materiali": [
            {
                "macc": "CERAMICA",
                "macq": 1,
                "macl": None,
                "macd": None,
                "macp": None,
                "mas": None,
            }
        ],
        "cdgg": "proprietà Stato",
        "cmpd": str(datetime.now().year),
        "cmpn": ["Rossi, Mario"],
        "fur": ["Bianchi, Anna"],
    }


def test_tma_schema_forces_tsk_and_lir_and_pads_nctn():
    payload = base_payload()
    model = SchedaTMACreate(**payload)
    assert model.tsk == "TMA"
    assert model.lir == "I"
    assert model.nctn == "00000123"


def test_tma_schema_rejects_macq_zero():
    payload = base_payload()
    payload["materiali"][0]["macq"] = 0
    with pytest.raises(ValidationError):
        SchedaTMACreate(**payload)


def test_tma_schema_rejects_cmpd_out_of_range():
    payload = base_payload()
    payload["cmpd"] = "1899"
    with pytest.raises(ValidationError):
        SchedaTMACreate(**payload)


def test_tma_schema_defaults_adsp_to_2():
    payload = base_payload()
    model = SchedaTMACreate(**payload)
    assert model.adsp == 2

