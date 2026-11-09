"""DWG R2000 скважин паспорта через dxf2dwg со сверкой обратным чтением (TASK-015, PR 4, §4).

Реальные утилиты LibreDWG есть только в Docker-образе API; без них реальный
тест пропускается, а логика сверки и отката проверяется поддельными
утилитами (как в `tests/test_spatial_dwg.py`).
"""
from __future__ import annotations

import io
import stat
from datetime import date
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
    return holes_dxf(context66(), revision_no=1, issued_on=date(2026, 11, 9))


def _empty_dxf() -> bytes:
    stream = io.StringIO()
    ezdxf.new("R2000").write(stream)
    return stream.getvalue().encode("utf-8")


def test_without_writer_falls_back_to_dxf(dxf66, monkeypatch):
    monkeypatch.setenv("BLASTEX_DXF2DWG", "/nowhere/dxf2dwg")
    exported = holes_dwg(dxf66)
    assert (exported.format, exported.data, exported.warning) == ("dxf", dxf66, DWG_FALLBACK_WARNING)


def test_writer_failure_falls_back_to_dxf(dxf66, tmp_path, monkeypatch):
    monkeypatch.setenv("BLASTEX_DXF2DWG", _script(tmp_path, "w", "exit 1\n"))
    exported = holes_dwg(dxf66)
    assert (exported.format, exported.warning) == ("dxf", DWG_FALLBACK_WARNING)


def test_round_trip_passes_and_dwg_is_returned(dxf66, tmp_path, monkeypatch):
    # «DWG» — копия DXF, обратное чтение — снова копия: сверка совпадает.
    monkeypatch.setenv("BLASTEX_DXF2DWG", _script(tmp_path, "w", 'cat "$IN" > "$OUT"\n'))
    monkeypatch.setenv("BLASTEX_DWG_CONVERTER", _script(tmp_path, "r", 'cat "$IN" > "$OUT"\n'))
    exported = holes_dwg(dxf66)
    assert (exported.format, exported.data, exported.warning) == ("dwg", dxf66, None)


def test_mismatch_on_read_back_falls_back_to_dxf(dxf66, tmp_path, monkeypatch):
    empty = tmp_path / "empty.dxf"
    empty.write_bytes(_empty_dxf())
    monkeypatch.setenv("BLASTEX_DXF2DWG", _script(tmp_path, "w", 'printf "AC1015" > "$OUT"\n'))
    monkeypatch.setenv("BLASTEX_DWG_CONVERTER", _script(tmp_path, "r", f'cp "{empty}" "$OUT"\n'))
    exported = holes_dwg(dxf66)
    assert (exported.format, exported.data, exported.warning) == ("dxf", dxf66, DWG_FALLBACK_WARNING)


def test_shifted_coordinates_on_read_back_fall_back_to_dxf(dxf66, tmp_path, monkeypatch):
    # Устье 1 в обратном чтении сдвинуто на 2 мм — больше допуска 1 мм.
    shifted = tmp_path / "shifted.dxf"
    shifted.write_bytes(dxf66.replace(b"1472880.04\n", b"1472880.042\n"))
    assert shifted.read_bytes() != dxf66
    monkeypatch.setenv("BLASTEX_DXF2DWG", _script(tmp_path, "w", 'printf "AC1015" > "$OUT"\n'))
    monkeypatch.setenv("BLASTEX_DWG_CONVERTER", _script(tmp_path, "r", f'cp "{shifted}" "$OUT"\n'))
    assert holes_dwg(dxf66).format == "dxf"


def test_unreadable_read_back_falls_back_to_dxf(dxf66, tmp_path, monkeypatch):
    monkeypatch.setenv("BLASTEX_DXF2DWG", _script(tmp_path, "w", 'printf "AC1015" > "$OUT"\n'))
    monkeypatch.setenv("BLASTEX_DWG_CONVERTER", _script(tmp_path, "r", 'printf "not a dxf" > "$OUT"\n'))
    assert holes_dwg(dxf66).format == "dxf"


@pytest.mark.skipif(find_writer() is None or find_converter() is None, reason="нет dxf2dwg или dwg2dxf (LibreDWG)")
def test_real_dwg_round_trip(dxf66):
    exported = holes_dwg(dxf66)
    assert exported.format == "dwg", exported.warning
    assert exported.data[:6] == b"AC1015"
    assert holes_dwg(dxf66).data == exported.data

    from design.spatial.dwg import dwg_to_dxf

    doc = ezdxf.read(io.StringIO(dwg_to_dxf(exported.data, "holes.dwg").decode("utf-8"), newline=None))
    msp = doc.modelspace()
    assert len(msp.query('POINT[layer=="BLX_HOLE"]')) == 196
    source = {str(row[0]): (float(row[1]), float(row[2]), float(row[3])) for row in _block66_rows()}
    for ref in msp.query('INSERT[layer=="BLX_HOLE"]'):
        x, y, z = source[ref.get_attrib_text("NUM")]
        assert tuple(ref.dxf.insert) == pytest.approx((x, y, z), abs=0.001)
        assert ref.get_attrib_text("DEPTH")
    info = msp.query('MTEXT[layer=="BLX_INFO"]')[0].plain_text()
    assert "Паспорт на бурение № 66-26/Б" in info


def test_crlf_read_back_is_accepted(dxf66, tmp_path, monkeypatch):
    # `dwg2dxf` пишет концы строк CRLF — сверка их переводит, а не откатывается.
    crlf = tmp_path / "crlf.dxf"
    crlf.write_bytes(dxf66.replace(b"\n", b"\r\n"))
    monkeypatch.setenv("BLASTEX_DXF2DWG", _script(tmp_path, "w", 'printf "AC1015" > "$OUT"\n'))
    monkeypatch.setenv("BLASTEX_DWG_CONVERTER", _script(tmp_path, "r", f'cp "{crlf}" "$OUT"\n'))
    exported = holes_dwg(dxf66)
    assert (exported.format, exported.data) == ("dwg", b"AC1015")
