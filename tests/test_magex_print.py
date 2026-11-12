"""Печать наряда-путёвки с QR MagEX (TASK-018 PR 7, §6) на блоке 66."""
from __future__ import annotations

import copy
import io
import json

import pytest
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import KeepInFrame, Table

from design.magex import jws
from design.mass_blast_layers import layer_seed, naryad_lines, naryad_totals
from design.reporting.mass_blast import frame
from design.reporting.mass_blast.layers import layer_part, naryad_story, render_layer_document
from design.reporting.mass_blast.qr import QR_QUIET_MODULES, QR_SIZE, QrFlowable, qr_matrix
from tests.magex_contract import FIXTURES
from tests.mass_blast_block66 import context66, payload66

pdfium = pytest.importorskip("pypdfium2")


def _key() -> jws.SigningKey:
    return jws.load_signing_key((FIXTURES / "keys" / "TEST-ONLY-private.pem").read_text(), "TEST-ONLY-magex-fixture")


@pytest.fixture(scope="module")
def revision() -> dict:
    context = context66(payload=payload66(requisites={"project_no": "66-26", "contractor_name": "ООО «Комплексные решения»"}))
    seed = layer_seed("NARYAD", context)
    payload = {"number": "66-26", "issue_date": "2026-10-14", "warehouse": "Склад ВМ № 1"}
    view = {"lines": naryad_lines(seed, payload, {"primers": 2, "nsi": 3, "starters": 2})}
    view["totals"] = naryad_totals(seed, view["lines"])
    return {"kind": "NARYAD", "seed": seed, "payload": payload, "view": view}


def _online(revision: dict, name: str = "large") -> dict:
    """Ревизия наряда, принятая MagEX: строка — пример контракта «20 позиций на 8 блоков» (1 953 знака)."""

    token = jws.sign_naryad(json.loads((FIXTURES / "naryads" / f"{name}.json").read_text()), _key())
    online = copy.deepcopy(revision)
    online["magex"] = {"mode": "ONLINE", "ver": 3, "kid": "TEST-ONLY-magex-fixture", "jws": token,
                       "wh": "a266838a-bd9e-5586-a1a5-77506af4e056", "num": "66-26", "lines": []}
    return online


def _flowables(items):
    for item in items:
        yield item
        if isinstance(item, KeepInFrame):
            yield from _flowables(item._content)
        if isinstance(item, Table):
            for row in item._cellvalues:
                for cell in row:
                    yield from _flowables(cell if isinstance(cell, (list, tuple)) else [cell])


def test_qr_is_the_accepted_jws_40mm_level_l(revision):
    online = _online(revision)
    width = frame.frame_width(True, layer_part(online).margins)
    story = naryad_story(online, width)
    codes = [item for item in _flowables(story) if isinstance(item, QrFlowable)]
    assert len(codes) == 1
    code = codes[0]
    assert code.value == online["magex"]["jws"]
    assert code.size == QR_SIZE and code.matrix == qr_matrix(online["magex"]["jws"])
    assert code.quiet == QR_QUIET_MODULES * code.module
    # Форма 4 помещается на лист без сжатия: QR печатается 40 × 40 мм, а не меньше.
    _page_w, page_h = frame.landscape(frame.A4)
    keep = story[0]
    frame.register_fonts()
    keep.canv = Canvas(io.BytesIO())
    keep.wrap(width, page_h - 23 * 2.834645669)
    assert getattr(keep, "_scale", 1.0) == pytest.approx(1.0)


def test_qr_print_is_one_page_with_caption_and_actual_size(revision):
    online = _online(revision)
    assert layer_part(online).actual_size is True
    pdf = render_layer_document(online)
    document = pdfium.PdfDocument(pdf)
    assert len(document) == 1
    text = document[0].get_textpage().get_text_range()
    assert "№ 66-26 / версия 3 / Склад ВМ № 1" in text
    assert b"/PrintScaling /None" in pdf


def test_offline_naryad_is_marked_and_without_qr(revision):
    offline = copy.deepcopy(revision)
    offline["magex"] = {"mode": "OFFLINE", "reason": "Не задан адрес MagEX."}
    text = pdfium.PdfDocument(render_layer_document(offline))[0].get_textpage().get_text_range()
    assert "вне учёта MagEX" in text
    assert not any(isinstance(item, QrFlowable) for item in _flowables(naryad_story(offline, 700)))


def test_revision_without_magex_prints_as_before(revision):
    """Ревизии до PR 7 и при выключенном флаге: печать та же (раскладка без QR и пометки)."""

    assert render_layer_document(revision) == render_layer_document(copy.deepcopy(revision))
    text = pdfium.PdfDocument(render_layer_document(revision))[0].get_textpage().get_text_range()
    assert "MagEX" not in text and layer_part(revision).actual_size is False
