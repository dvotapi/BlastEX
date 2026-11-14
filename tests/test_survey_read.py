import io
from pathlib import Path

import openpyxl
import pytest

from design.survey.read import SurveyedPoint, SurveyReadError, read_survey

FIX = Path("tests/fixtures/drill_passport/stakeout")
CSV_TEXT = "﻿№;Восток;Север;Отметка;Глубина;Вода\n1-01;1472880,04;593722,99;419,21;12,4;да\n"


def test_pnezd_roundtrip_block66():
    f = read_survey((FIX / "66_PNEZD_CSV.csv").read_bytes(), "66_PNEZD_CSV.csv")
    p = next(p for p in f.points if p.name == "66-001")
    # строка «66-001,593722.990,1472880.040,419.210,R1 L10.7»: N → y, E → x
    assert (p.y, p.x, p.z) == (593722.990, 1472880.040, 419.210)
    assert f.format == "PNEZD_CSV"
    assert len(f.sha256) == 64


def test_stakeout_description_is_not_depth():
    f = read_survey((FIX / "66_PNEZD_CSV.csv").read_bytes(), "66_PNEZD_CSV.csv")
    assert all(p.depth_m is None for p in f.points)


def test_penzd_txt_dxf_give_same_points_as_pnezd():
    base = {
        p.name: (round(p.x, 3), round(p.y, 3))
        for p in read_survey((FIX / "66_PNEZD_CSV.csv").read_bytes(), "a.csv").points
    }
    assert len(base) > 100
    for name in ("66_PENZD_CSV.csv", "66_PNEZ_TXT.txt", "66_DXF_POINTS.dxf"):
        other = {
            p.name: (round(p.x, 3), round(p.y, 3))
            for p in read_survey((FIX / name).read_bytes(), name, format=name[3:-4]).points
        }
        assert other == base


def test_format_detected_by_extension():
    assert read_survey((FIX / "66_PNEZ_TXT.txt").read_bytes(), "x.txt").format == "PNEZ_TXT"
    assert read_survey((FIX / "66_DXF_POINTS.dxf").read_bytes(), "x.dxf").format == "DXF_POINTS"


def test_header_row_skipped():
    raw = b"Point,Northing,Easting,Elevation,Description\r\n1-01,593722.990,1472880.040,419.210,R1\r\n"
    f = read_survey(raw, "s.csv", format="PNEZD_CSV")
    assert [p.name for p in f.points] == ["1-01"]


def test_table_semicolon_decimal_comma_bom_cp1251():
    for enc in ("utf-8", "cp1251"):
        raw = CSV_TEXT.encode(enc, errors="ignore") if enc == "cp1251" else CSV_TEXT.encode(enc)
        p = read_survey(raw, "s.csv").points[0]
        assert (p.name, p.x, p.y, p.z, p.depth_m, p.wet) == ("1-01", 1472880.04, 593722.99, 419.21, 12.4, True)


def test_table_russian_xy_detected_by_columns():
    raw = "Номер;X;Y;H\n1-01;593722,99;1472880,04;419,21\n".encode()
    f = read_survey(raw, "s.csv")
    assert f.columns["north"] == "X" and f.points[0].y == 593722.99  # по-русски X — север
    assert any("X — север" in w for w in f.warnings)


def test_table_swap_xy():
    raw = "Номер;X;Y\n1-01;1472880,04;593722,99\n".encode()
    p = read_survey(raw, "s.csv", swap_xy=True).points[0]
    assert (p.x, p.y) == (1472880.04, 593722.99)


def test_table_explicit_columns_win():
    raw = "a;b;c\n1-01;1472880,04;593722,99\n".encode()
    f = read_survey(raw, "s.csv", format="TABLE", columns={"name": "a", "east": "b", "north": "c"})
    assert (f.points[0].x, f.points[0].y) == (1472880.04, 593722.99)


def test_table_angle_azimuth_water_and_duplicates():
    raw = "Скв;E;N;Угол;Азимут;Уровень воды;Обводн\nA;1;2;75;90;3,5;нет\nA;3;4;;;;+\n".encode()
    pts = read_survey(raw, "s.csv").points
    assert len(pts) == 2
    assert (pts[0].angle_deg, pts[0].azimuth_deg, pts[0].water_depth_m, pts[0].wet) == (75, 90, 3.5, False)
    assert pts[1].angle_deg is None and pts[1].wet is True
    assert pts[0].line == 2 and pts[1].line == 3


def test_xlsx_table():
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["№", "Восток", "Север", "Отметка", "Глубина", "Вода"])
    ws.append(["1-01", 1472880.04, 593722.99, 419.21, 12.4, "да"])
    buf = io.BytesIO()
    wb.save(buf)
    f = read_survey(buf.getvalue(), "s.xlsx")
    assert f.format == "TABLE"
    p = f.points[0]
    assert (p.name, p.x, p.y, p.z, p.depth_m, p.wet) == ("1-01", 1472880.04, 593722.99, 419.21, 12.4, True)


def test_point_dict_roundtrip_skips_none():
    p = SurveyedPoint("a", 1.0, 2.0, depth_m=3.0, line=4)
    d = p.to_dict()
    assert "z" not in d and "wet" not in d
    assert SurveyedPoint.from_dict(d) == p


def test_empty_or_garbage_raises():
    with pytest.raises(SurveyReadError):
        read_survey(b"", "s.csv")
    with pytest.raises(SurveyReadError):
        read_survey(b"\x00\x01\x02garbage", "s.dxf")
    with pytest.raises(SurveyReadError):
        read_survey("только;заголовок\n".encode(), "s.csv", format="TABLE")
