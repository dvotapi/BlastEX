"""Файл выноса скважин для GNSS-приёмника (TASK-015, PR 5, спека §5)."""
from __future__ import annotations

from design.export_survey import BUILTIN_PROFILES, DEFAULT_STAKEOUT_PROFILE, stakeout_snapshot


def test_stakeout_snapshot_builtin_profiles() -> None:
    snapshot = stakeout_snapshot({}, None)
    assert DEFAULT_STAKEOUT_PROFILE == "PNEZD_CSV"
    assert snapshot["default"] == "PNEZD_CSV"
    assert list(snapshot["profiles"]) == ["PNEZD_CSV", "PENZD_CSV", "PNEZ_TXT", "DXF_POINTS"]
    assert snapshot["profiles"] == BUILTIN_PROFILES
    assert snapshot["profiles"]["PENZD_CSV"] == {
        "name": "CSV: точка, восток, север, отметка, описание", "format": "PENZD_CSV",
        "header": False, "elevation": True, "include_toe": False,
    }


def test_stakeout_snapshot_reference_records() -> None:
    records = {
        "TRIMBLE": {"name": "Trimble Access", "format": "PENZD_CSV", "header": True},
        "PNEZD_CSV": {"name": "Без отметок", "format": "PNEZD_CSV", "elevation": False},
    }
    snapshot = stakeout_snapshot(records, "TRIMBLE")
    assert snapshot["default"] == "TRIMBLE"
    assert snapshot["profiles"]["TRIMBLE"] == {
        "name": "Trimble Access", "format": "PENZD_CSV", "header": True, "elevation": True, "include_toe": False,
    }
    # Запись с кодом встроенного профиля его заменяет.
    assert snapshot["profiles"]["PNEZD_CSV"]["elevation"] is False
    assert len(snapshot["profiles"]) == 5


def test_stakeout_snapshot_unknown_default_falls_back() -> None:
    assert stakeout_snapshot({}, "NOPE")["default"] == "PNEZD_CSV"


# --- файл выноса ------------------------------------------------------------

import io
import math
import os
from copy import deepcopy
from pathlib import Path

import ezdxf
import pytest

from design.export_survey import (
    STAKEOUT_EXTENSIONS,
    StakeoutError,
    point_name,
    stakeout_file,
    stakeout_profile,
)
from tests.drill_passport_context import context66
from tests.test_drilling_passport import _block66_rows

GOLDEN = Path(__file__).parent / "fixtures" / "drill_passport" / "stakeout"
FIRST_LINE = "66-001,593722.990,1472880.040,419.210,R1 L10.7"


def _file(context: dict, code: str | None = None, **options) -> bytes:
    _, profile = stakeout_profile(context, code)
    return stakeout_file(context, {**profile, **options})


def _lines(data: bytes) -> list[str]:
    text = data.decode("ascii")
    assert text.endswith("\r\n")
    return text[:-2].split("\r\n")


def _inclined(context: dict, index: int = 100) -> dict:
    """Скважина не первого ряда с наклоном β 75°, азимут 120°."""

    result = deepcopy(context)
    row = result["holes"][index]
    assert not row["first_row"]
    dip, azimuth, length = 75.0, 120.0, row["length_m"]
    c = row["collar"]
    horizontal = length * math.cos(math.radians(dip))
    row.update(
        dip_deg=dip,
        azimuth_deg=azimuth,
        toe={
            "x": c["x"] + horizontal * math.sin(math.radians(azimuth)),
            "y": c["y"] + horizontal * math.cos(math.radians(azimuth)),
            "z": c["z"] - length * math.sin(math.radians(dip)),
        },
    )
    return result


def test_pnezd_block66_matches_spec() -> None:
    data = _file(context66(), "PNEZD_CSV")
    assert not data.startswith(b"\xef\xbb\xbf")
    assert b"\n" not in data.replace(b"\r\n", b"")
    lines = _lines(data)
    assert len(lines) == 196
    assert lines[0] == FIRST_LINE
    for line, (_, x, y, z, *_rest) in zip(lines, _block66_rows()):
        _, north, east, elevation, _ = line.split(",")
        assert float(north) == pytest.approx(float(y), abs=0.001)
        assert float(east) == pytest.approx(float(x), abs=0.001)
        assert float(elevation) == pytest.approx(float(z), abs=0.001)


@pytest.mark.parametrize("code", ["PNEZD_CSV", "PENZD_CSV", "PNEZ_TXT", "DXF_POINTS"])
def test_profiles_match_snapshots(code: str) -> None:
    data = _file(context66(), code)
    assert data == _file(context66(), code)
    golden = GOLDEN / f"66_{code}.{STAKEOUT_EXTENSIONS[code]}"
    if os.environ.get("BLASTEX_UPDATE_GOLDEN") == "1":
        golden.parent.mkdir(parents=True, exist_ok=True)
        golden.write_bytes(data)
    assert data == golden.read_bytes()


def test_header_and_elevation_options() -> None:
    context = context66()
    assert _lines(_file(context, "PNEZD_CSV", header=True))[:2] == [
        "Point,Northing,Easting,Elevation,Description",
        FIRST_LINE,
    ]
    assert _lines(_file(context, "PENZD_CSV", header=True))[:2] == [
        "Point,Easting,Northing,Elevation,Description",
        "66-001,1472880.040,593722.990,419.210,R1 L10.7",
    ]
    assert _lines(_file(context, "PNEZD_CSV", elevation=False))[0] == "66-001,593722.990,1472880.040,,R1 L10.7"
    assert _lines(_file(context, "PNEZ_TXT"))[0] == "66-001 593722.990 1472880.040 419.210"
    assert _lines(_file(context, "PNEZ_TXT", elevation=False))[0] == "66-001 593722.990 1472880.040"
    assert _lines(_file(context, "PNEZ_TXT", header=True))[0] == "Point Northing Easting Elevation"


def test_inclined_description_and_toe() -> None:
    context = _inclined(context66())
    row = context["holes"][100]
    name = point_name("66", row["number"])
    lines = _lines(_file(context, "PNEZD_CSV"))
    assert lines[100].split(",")[-1] == f"L{row['length_m']:.1f} A75 AZ120"
    with_toe = _lines(_file(context, "PNEZD_CSV", include_toe=True))
    assert len(with_toe) == 197
    toe = with_toe[101].split(",")
    assert toe[0] == f"{name}_T"
    assert float(toe[1]) == pytest.approx(row["toe"]["y"], abs=0.001)
    assert float(toe[2]) == pytest.approx(row["toe"]["x"], abs=0.001)
    assert float(toe[3]) == pytest.approx(row["toe"]["z"], abs=0.001)
    assert toe[4] == "TOE"


def test_point_names() -> None:
    assert point_name("66", "1") == "66-001"
    assert point_name("66", "1-01") == "66-1-01"
    assert point_name("66", "5-08T") == "66-5-08T"
    assert point_name("66А", "Р1") == "66A-R1"
    assert point_name("", "12") == "012"
    assert point_name("66", "1,2 б") == "66-1_2_b"


def test_name_conflict_and_length_errors() -> None:
    context = context66()
    context["holes"][0]["number"] = "Р1"
    context["holes"][1]["number"] = "R1"
    with pytest.raises(StakeoutError, match="Р1") as error:
        _file(context, "PNEZD_CSV")
    assert "R1" in str(error.value)
    context = context66()
    context["holes"][0]["number"] = "1234567890123-01"
    with pytest.raises(StakeoutError, match="16"):
        _file(context, "PNEZD_CSV")


def test_non_ascii_is_never_written() -> None:
    context = context66()
    context["passport"]["payload"]["block"] = "66Б"
    context["holes"][0]["number"] = "Ж-1"
    for code in STAKEOUT_EXTENSIONS:
        _file(context, code).decode("ascii")


def test_dxf_points() -> None:
    data = _file(context66(), "DXF_POINTS")
    data.decode("ascii")
    doc = ezdxf.read(io.StringIO(data.decode("ascii")))
    assert doc.dxfversion == "AC1009"
    msp = doc.modelspace()
    points = [e for e in msp if e.dxftype() == "POINT"]
    texts = [e for e in msp if e.dxftype() == "TEXT"]
    assert len(points) == len(texts) == 196
    assert {e.dxf.layer for e in [*points, *texts]} == {"BLX_HOLE"}
    assert texts[0].dxf.text == "66-001"
    x, y, z = points[0].dxf.location
    assert (x, y, z) == pytest.approx((1472880.04, 593722.99, 419.21), abs=0.001)


def test_profile_resolution() -> None:
    context = context66()
    assert "stakeout" not in context
    assert stakeout_profile(context, None)[0] == "PNEZD_CSV"
    with pytest.raises(StakeoutError, match="PENZD_CSV"):
        stakeout_profile(context, "GSI")
    context["stakeout"] = {"default": "MY", "profiles": {"MY": {"name": "Мой", "format": "PNEZ_TXT", "header": False, "elevation": True, "include_toe": False}}}
    code, profile = stakeout_profile(context, None)
    assert code == "MY" and profile["format"] == "PNEZ_TXT"


def test_dxf_points_opens_in_libreoffice(tmp_path) -> None:
    import shutil
    import subprocess

    from tests.libreoffice import convert

    if shutil.which("pdftotext") is None:
        pytest.skip("Нет pdftotext")
    source = tmp_path / "points.dxf"
    source.write_bytes(_file(context66(), "DXF_POINTS"))
    pdf = convert(source, "pdf", tmp_path)
    text = subprocess.run(["pdftotext", str(pdf), "-"], check=True, capture_output=True, text=True).stdout
    assert sum(1 for word in text.split() if word.startswith("66-")) == 196


def test_long_block_error_names_the_field() -> None:
    context = context66()
    context["passport"]["payload"]["block"] = "Уступ 120/108"
    with pytest.raises(StakeoutError, match="«Блок»"):
        _file(context, "PNEZD_CSV")


def test_builtin_profiles_are_reference_records() -> None:
    from cost.v2.models import ReferenceItem
    from cost.v2.references import default_reference_sections, validate_reference_sections

    sections = dict(default_reference_sections())
    assert [item.code for item in sections["stakeout_profiles"]] == list(BUILTIN_PROFILES)
    assert {item.code: item.payload["format"] for item in sections["stakeout_profiles"]} == {
        code: code for code in BUILTIN_PROFILES
    }
    sections["sites"] = (ReferenceItem(code="ZHK", name="Жуков Камень", payload={"stakeout_profile_code": "DXF_POINTS"}),)
    issues = [issue for issue in validate_reference_sections(sections) if issue.section == "sites" and "DXF_POINTS" in issue.message]
    assert issues == []


# --- правки по /code-review PR #170 -----------------------------------------


def test_names_differing_only_in_case_clash() -> None:
    """Полевые программы часто не различают регистр имён точек."""

    context = context66()
    context["holes"][0]["number"] = "1-01a"
    context["holes"][1]["number"] = "1-01A"
    with pytest.raises(StakeoutError, match="1-01a"):
        _file(context, "PNEZD_CSV")


def test_leading_zeros_are_kept() -> None:
    assert point_name("66", "01") == "66-01"
    assert point_name("66", "0012") == "66-0012"
    assert point_name("66", "7") == "66-007"
    context = context66()
    context["holes"][1]["number"] = "01"
    lines = _lines(_file(context, "PNEZD_CSV"))
    assert [line.split(",")[0] for line in lines[:2]] == ["66-001", "66-01"]


def test_azimuth_near_north_is_zero_everywhere() -> None:
    from design.export_survey import holes_dxf

    context = _inclined(context66())
    context["holes"][100]["azimuth_deg"] = 359.6
    assert _lines(_file(context, "PNEZD_CSV"))[100].endswith("A75 AZ0")
    doc = ezdxf.read(io.StringIO(holes_dxf(context, revision_no=1).decode("utf-8")))
    number = context["holes"][100]["number"]
    insert = next(e for e in doc.modelspace().query("INSERT") if e.get_attrib_text("NUM") == number)
    assert insert.get_attrib_text("AZIM") == "0"


def test_dxf_points_always_carry_collar_elevation() -> None:
    """В DXF поле отметки не оставить пустым: Z = 0 приёмник принял бы за проект."""

    doc = ezdxf.read(io.StringIO(_file(context66(), "DXF_POINTS", elevation=False).decode("ascii")))
    point = next(e for e in doc.modelspace() if e.dxftype() == "POINT")
    assert point.dxf.location[2] == pytest.approx(419.21, abs=0.001)


def test_dxf_points_extents_cover_the_block() -> None:
    doc = ezdxf.read(io.StringIO(_file(context66(), "DXF_POINTS").decode("ascii")))
    xs = [e.dxf.location[0] for e in doc.modelspace() if e.dxftype() == "POINT"]
    ys = [e.dxf.location[1] for e in doc.modelspace() if e.dxftype() == "POINT"]
    low, high = doc.header["$EXTMIN"], doc.header["$EXTMAX"]
    assert low[0] <= min(xs) and low[1] <= min(ys)
    assert high[0] >= max(xs) and high[1] >= max(ys)
    assert high[0] - low[0] < 1000 and high[1] - low[1] < 1000
