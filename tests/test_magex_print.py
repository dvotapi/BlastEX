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
    # QR — вне сжимаемой части формы: 40 × 40 мм при любом её объёме.
    assert not any(isinstance(item, QrFlowable) for item in _flowables([story[-1]]))
    assert isinstance(story[-1], KeepInFrame)


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


def test_signed_blaster_permit_and_vehicle_are_printed(revision):
    online = _online(revision)
    online["magex"]["print"] = {"blaster_name": "Трегубов Александр Иванович", "blaster_index": "ЮФ60АВ"}
    online["payload"] = {**online["payload"], "permit_number": "РВ-66", "permit_date": "2026-01-15",
                         "vehicle_model": "КамАЗ 43118", "vehicle_plate": "А123ВС96"}
    text = pdfium.PdfDocument(render_layer_document(online))[0].get_textpage().get_text_range()
    for expected in ("Трегубов Александр Иванович", "ЮФ60АВ", "№ РВ-66 от 15.01.2026", "КамАЗ 43118 А123ВС96"):
        assert expected in text


def test_structured_fields_win_over_legacy_text(revision):
    """Печать — как подписанная выписка: раздельные поля главнее прежней строки (замечание Codex)."""

    online = _online(revision)
    online["payload"] = {**online["payload"], "vehicle": "ГАЗ старый", "permit": "старое разрешение",
                         "vehicle_model": "КамАЗ 43118", "vehicle_plate": "А123ВС96",
                         "permit_number": "РВ-66", "permit_date": "2026-01-15"}
    text = pdfium.PdfDocument(render_layer_document(online))[0].get_textpage().get_text_range()
    assert "КамАЗ 43118 А123ВС96" in text and "№ РВ-66 от 15.01.2026" in text
    assert "ГАЗ старый" not in text and "старое разрешение" not in text


def test_qr_keeps_40mm_on_a_crowded_form(revision):
    online = _online(revision)
    online["seed"] = {**online["seed"], "blocks": [{**online["seed"]["blocks"][0], "code": f"B{index}"} for index in range(50)]}
    pdf = render_layer_document(online)
    document = pdfium.PdfDocument(pdf)
    assert len(document) == 1
    story = naryad_story(online, frame.frame_width(True, layer_part(online).margins))
    frame.register_fonts()
    keep = story[-1]
    keep.canv = Canvas(io.BytesIO())
    keep.wrap(keep.maxWidth, keep.maxHeight)
    assert keep._scale > 1.0  # форма сжата (ReportLab: делитель масштаба), а QR — нет
