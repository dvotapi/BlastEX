"""DWG R2000 скважин паспорта через dxf2dwg со сверкой обратным чтением (TASK-015, PR 4, §4).

Реальные утилиты LibreDWG есть только в Docker-образе API; без них реальный
тест пропускается, а логика сверки и отката проверяется поддельными
утилитами (как в `tests/test_spatial_dwg.py`).
"""
from __future__ import annotations

import io
import stat
from pathlib import Path

import ezdxf
import pytest

from design.export_survey import DWG_FALLBACK_WARNING, holes_dwg, holes_dxf
from design.spatial.dwg import find_converter, find_writer
from tests.drill_passport_context import context66
from tests.test_drilling_passport import _block66_rows

_ARGS = 'OUT=""; IN=""\nwhile [ $# -gt 0 ]; do\n  if [ "$1" = "-o" ]; then OUT="$2"; shift; fi\n  IN="$1"; shift\ndone\n'


def _script(tmp_path: Path, name: str, body: str) -> str:
    script = tmp_path / name
    script.write_text("#!/bin/sh\n" + _ARGS + body)
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    return str(script)


@pytest.fixture(scope="module")
def dxf66() -> bytes:
    return holes_dxf(context66(), revision_no=1)


def _empty_dxf() -> bytes:
    stream = io.StringIO()
    ezdxf.new("R2000").write(stream)
    return stream.getvalue().encode("utf-8")


def _round_trip(tmp_path: Path, monkeypatch, read_back: bytes, written: str = "AC1015 dwg") -> None:
    """Подделки: dxf2dwg пишет `written`, dwg2dxf возвращает `read_back`."""

    back = tmp_path / "back.dxf"
    back.write_bytes(read_back)
    monkeypatch.setenv("BLASTEX_DXF2DWG", _script(tmp_path, "w", f'printf "{written}" > "$OUT"\n'))
    monkeypatch.setenv("BLASTEX_DWG_CONVERTER", _script(tmp_path, "r", f'cp "{back}" "$OUT"\n'))


def test_without_writer_falls_back_to_dxf(dxf66, monkeypatch):
    monkeypatch.setenv("BLASTEX_DXF2DWG", "/nowhere/dxf2dwg")
    exported = holes_dwg(dxf66)
    assert (exported.format, exported.data, exported.warning) == ("dxf", dxf66, DWG_FALLBACK_WARNING)


def test_writer_failure_falls_back_to_dxf(dxf66, tmp_path, monkeypatch):
    monkeypatch.setenv("BLASTEX_DXF2DWG", _script(tmp_path, "w", "exit 1\n"))
    exported = holes_dwg(dxf66)
    assert (exported.format, exported.warning) == ("dxf", DWG_FALLBACK_WARNING)


def test_round_trip_passes_and_dwg_is_returned(dxf66, tmp_path, monkeypatch):
    _round_trip(tmp_path, monkeypatch, dxf66)
    exported = holes_dwg(dxf66)
    assert (exported.format, exported.data, exported.warning) == ("dwg", b"AC1015 dwg", None)


def test_writer_output_without_r2000_signature_falls_back(dxf66, tmp_path, monkeypatch):
    # dxf2dwg «записал» копию DXF — это не DWG R2000.
    _round_trip(tmp_path, monkeypatch, dxf66, written="  0")
    assert holes_dwg(dxf66).format == "dxf"


def _changed(**changes) -> bytes:
    context = context66()
    for key, value in changes.items():
        if key == "passport_no":
            context["passport"]["passport_no"] = value
        else:
            context["holes"][0][key] = value
    return holes_dxf(context, revision_no=1)


def test_changed_depth_on_read_back_falls_back(dxf66, tmp_path, monkeypatch):
    _round_trip(tmp_path, monkeypatch, _changed(length_m=99.9))
    assert holes_dwg(dxf66).format == "dxf"


def test_changed_info_text_on_read_back_falls_back(dxf66, tmp_path, monkeypatch):
    _round_trip(tmp_path, monkeypatch, _changed(passport_no="99-99/Б"))
    assert holes_dwg(dxf66).format == "dxf"


def test_moved_contour_vertex_on_read_back_falls_back(dxf66, tmp_path, monkeypatch):
    # Первая вершина контура блока 66 сдвинута на 2 мм.
    vertex = b"1472845.45\n"
    assert dxf66.index(vertex) < dxf66.index(b"BLX_HOLE\n 10\n")
    _round_trip(tmp_path, monkeypatch, dxf66.replace(vertex, b"1472845.452\n", 1))
    assert holes_dwg(dxf66).format == "dxf"


def test_moved_toe_line_end_on_read_back_falls_back(tmp_path, monkeypatch):
    # Сдвинут только конец LINE устье → забой (точка забоя на месте).
    from tests.test_export_survey_dxf import _with_inclined

    dxf = holes_dxf(_with_inclined(context66()), revision_no=1)
    doc = ezdxf.read(io.StringIO(dxf.decode("utf-8")))
    end_x = doc.modelspace().query('LINE[layer=="BLX_TOE"]')[0].dxf.end.x
    tag = f"\n 11\n{end_x}\n".encode()
    assert dxf.count(tag) == 1
    _round_trip(tmp_path, monkeypatch, dxf.replace(tag, f"\n 11\n{end_x + 0.01}\n".encode()))
    assert holes_dwg(dxf).format == "dxf"


@pytest.mark.parametrize("count", [1, -1], ids=["point-only", "point-and-insert"])
def test_shifted_collar_on_read_back_falls_back(dxf66, tmp_path, monkeypatch, count):
    # Устье 1 сдвинуто на 2 мм: только POINT (первое вхождение) или и вставка.
    shifted = dxf66.replace(b"1472880.04\n", b"1472880.042\n", count)
    assert shifted != dxf66
    _round_trip(tmp_path, monkeypatch, shifted)
    assert holes_dwg(dxf66).format == "dxf"


def test_mismatch_on_read_back_falls_back_to_dxf(dxf66, tmp_path, monkeypatch):
    _round_trip(tmp_path, monkeypatch, _empty_dxf())
    exported = holes_dwg(dxf66)
    assert (exported.format, exported.data, exported.warning) == ("dxf", dxf66, DWG_FALLBACK_WARNING)


def test_unreadable_read_back_falls_back_to_dxf(dxf66, tmp_path, monkeypatch):
    _round_trip(tmp_path, monkeypatch, b"not a dxf")
    assert holes_dwg(dxf66).format == "dxf"


@pytest.mark.skipif(find_writer() is None or find_converter() is None, reason="нет dxf2dwg или dwg2dxf (LibreDWG)")
def test_real_dwg_round_trip(dxf66):
    exported = holes_dwg(dxf66)
    assert exported.format == "dwg", exported.warning
    assert exported.data[:6] == b"AC1015"
    assert holes_dwg(dxf66).data == exported.data

    from design.spatial.dwg import dwg_to_dxf

    # dwg2dxf: UTF-8, CRLF, длинный MTEXT разрезан по байтам — как в сверке.
    back = dwg_to_dxf(exported.data, "holes.dwg").decode("utf-8", "surrogateescape")
    doc = ezdxf.read(io.StringIO(back, newline=None))
    msp = doc.modelspace()
    assert len(msp.query('POINT[layer=="BLX_HOLE"]')) == 196
    source = {str(row[0]): (float(row[1]), float(row[2]), float(row[3])) for row in _block66_rows()}
    for ref in msp.query('INSERT[layer=="BLX_HOLE"]'):
        x, y, z = source[ref.get_attrib_text("NUM")]
        assert tuple(ref.dxf.insert) == pytest.approx((x, y, z), abs=0.001)
        assert ref.get_attrib_text("DEPTH")
    info = msp.query('MTEXT[layer=="BLX_INFO"]')[0].plain_text()
    info = info.encode("utf-8", "surrogateescape").decode("utf-8")
    assert "Паспорт на бурение № 66-26/Б от 05.10.2026" in info
    assert "Линия подошвы — расчётная" in info
    assert len(msp.query('LWPOLYLINE[layer=="BLX_TOE_LINE"]')) == 1
    assert doc.styles.get("Standard").dxf.font == "arial.ttf"


def test_crlf_read_back_is_accepted(dxf66, tmp_path, monkeypatch):
    # `dwg2dxf` пишет концы строк CRLF — сверка их переводит, а не откатывается.
    _round_trip(tmp_path, monkeypatch, dxf66.replace(b"\n", b"\r\n"))
    exported = holes_dwg(dxf66)
    assert (exported.format, exported.data) == ("dwg", b"AC1015 dwg")


def test_mtext_split_inside_utf8_character_is_accepted(tmp_path, monkeypatch):
    # dwg2dxf режет длинный MTEXT на куски по 250 байт (группа 3) и может
    # разрезать двухбайтовую букву: сверка склеивает байты, а не символы.
    context = context66()
    context["crs"] = {"name": "МСК-66 зона 1", "epsg": None, "height_system": "Балтийская 1977"}
    dxf = holes_dxf(context, revision_no=1)
    # Значение MTEXT — после кода группы 1 (последний кусок) или 3 (первый из
    # нескольких, если текст длиннее 250 знаков).
    marker = "\nПаспорт".encode()
    assert dxf.count(marker) == 1
    start = dxf.index(marker) + 1
    code_start = dxf.rindex(b"\n", 0, start - 1) + 1
    code = dxf[code_start:start]
    assert code.strip() in (b"1", b"3")
    end = dxf.index(b"\n", start)
    value = dxf[start:end]
    split = dxf[:code_start] + b"  3\n" + value[:3] + b"\n" + code + value[3:] + dxf[end:]
    _round_trip(tmp_path, monkeypatch, split)
    assert holes_dwg(dxf).format == "dwg"


@pytest.mark.skipif(find_writer() is None or find_converter() is None, reason="нет dxf2dwg или dwg2dxf (LibreDWG)")
def test_real_dwg_with_inclined_hole_and_cyrillic_crs():
    from tests.test_export_survey_dxf import _with_inclined

    context = _with_inclined(context66())
    context["crs"] = {"name": "МСК-66 зона 1", "epsg": None, "height_system": "Балтийская 1977"}
    exported = holes_dwg(holes_dxf(context, revision_no=2))
    assert (exported.format, exported.warning) == ("dwg", None)
