import io
from pathlib import Path

import openpyxl
import pytest

import design.survey.read as survey_read
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


def test_table_headers_returned():
    raw = "Номер;X;Y;H\n1-01;593722,99;1472880,04;419,21\n".encode()
    assert read_survey(raw, "s.csv").headers == ["Номер", "X", "Y", "H"]
    assert read_survey((FIX / "66_PNEZ_TXT.txt").read_bytes(), "x.txt").headers == []


def test_table_missing_column_error_carries_headers():
    raw = "Пикет;Восточн;Северн\n1-01;1472880,04;593722,99\n".encode()
    with pytest.raises(SurveyReadError) as missing:
        read_survey(raw, "s.csv", format="TABLE")
    assert "Укажите её вручную" in str(missing.value)
    assert missing.value.headers == ["Пикет", "Восточн", "Северн"]
    with pytest.raises(SurveyReadError) as unknown:
        read_survey(raw, "s.csv", format="TABLE", columns={"name": "Нет такой"})
    assert unknown.value.headers == ["Пикет", "Восточн", "Северн"]
    f = read_survey(raw, "s.csv", format="TABLE", columns={"name": "Пикет", "east": "Восточн", "north": "Северн"})
    assert (f.points[0].name, f.points[0].x) == ("1-01", 1472880.04)


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


def test_size_and_row_caps(monkeypatch):
    monkeypatch.setattr(survey_read, "MAX_SURVEY_BYTES", 50)
    with pytest.raises(SurveyReadError):
        read_survey(b"1-01,1,2,3\n" * 10, "s.csv")
    monkeypatch.setattr(survey_read, "MAX_SURVEY_BYTES", 10_000_000)
    monkeypatch.setattr(survey_read, "MAX_SURVEY_ROWS", 3)
    with pytest.raises(SurveyReadError):
        read_survey(b"".join(b"%d,1,2,3\n" % i for i in range(10)), "s.csv", format="PNEZD_CSV")
    with pytest.raises(SurveyReadError):
        read_survey("№;E;N\n".encode() + b"".join(b"%d;1;2\n" % i for i in range(10)), "s.csv")
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["№", "E", "N"])
    for i in range(10):
        ws.append([str(i), 1, 2])
    buf = io.BytesIO()
    wb.save(buf)
    with pytest.raises(SurveyReadError):
        read_survey(buf.getvalue(), "s.xlsx")
    dxf = (FIX / "66_DXF_POINTS.dxf").read_bytes()
    with pytest.raises(SurveyReadError):
        read_survey(dxf, "s.dxf")


def test_dxf_unlabeled_point_warns():
    import ezdxf

    doc = ezdxf.new("R12")
    msp = doc.modelspace()
    msp.add_point((10, 20, 1))
    msp.add_text("A-1", height=0.4).set_placement((10.15, 20.15, 1))
    msp.add_point((50, 60, 1))
    stream = io.StringIO()
    doc.write(stream)
    f = read_survey(stream.getvalue().encode(), "s.dxf")
    assert [p.name for p in f.points] == ["A-1"]
    assert any("без подписи" in w for w in f.warnings)


def test_empty_wet_is_none_and_dash_too():
    raw = "№;E;N;Вода\nA;1;2;\nB;3;4;-\nC;5;6;нет\n".encode()
    assert [p.wet for p in read_survey(raw, "s.csv").points] == [None, None, False]


def test_quoted_decimal_comma_in_comma_csv():
    raw = '№,E,N,Глубина\nA,"1472880,04","593722,99","12,5"\n'.encode()
    p = read_survey(raw, "s.csv").points[0]
    assert (p.x, p.y, p.depth_m) == (1472880.04, 593722.99, 12.5)


def test_dxf_stacked_labels_fail_fast():
    import time

    import ezdxf

    doc = ezdxf.new("R12")
    msp = doc.modelspace()
    for i in range(500):
        msp.add_point((10, 20, 1))
        msp.add_text(f"A-{i}", height=0.4).set_placement((10.1, 20.1, 1))
    stream = io.StringIO()
    doc.write(stream)
    started = time.monotonic()
    with pytest.raises(SurveyReadError, match="Слишком много подписей"):
        read_survey(stream.getvalue().encode(), "s.dxf")
    assert time.monotonic() - started < 5


@pytest.mark.parametrize("name", ["66_PNEZD_CSV.csv", "66_PENZD_CSV.csv", "66_PNEZ_TXT.txt", "66_DXF_POINTS.dxf"])
def test_swap_xy_for_profiles_and_dxf(name):
    """«Поменять» действует на все форматы, а не только на таблицу."""

    raw = (FIX / name).read_bytes()
    plain = read_survey(raw, name, format=name[3:-4])
    swapped = read_survey(raw, name, format=name[3:-4], swap_xy=True)
    assert [(p.name, p.x, p.y) for p in swapped.points] == [(p.name, p.y, p.x) for p in plain.points]
    assert "Колонки востока и севера переставлены по запросу." in swapped.warnings
    assert "Колонки востока и севера переставлены по запросу." not in plain.warnings


@pytest.mark.parametrize("sep", ["\t", " ", "  "])
@pytest.mark.parametrize("dec", [".", ","])
def test_txt_table_with_header_tab_or_spaces(sep, dec):
    # Таблица в .txt с заголовком — колонки по заголовку, а не по позиции профиля PNEZ_TXT.
    values = ["1-01", "1472880.04", "593722.99", "419.21", "12.4"]
    rows = [["№", "Восток", "Север", "Отметка", "Глубина"], [v.replace(".", dec) for v in values]]
    raw = "\n".join(sep.join(r) for r in rows).encode()
    f = read_survey(raw, "s.txt")
    p = f.points[0]
    assert f.format == "TABLE"
    assert (p.name, p.x, p.y, p.z, p.depth_m) == ("1-01", 1472880.04, 593722.99, 419.21, 12.4)


def test_profile_from_file_name():
    # Файл выноса BlastEX называется по профилю — без выбора формата профиль берётся из имени.
    base = {p.name: (p.x, p.y) for p in read_survey((FIX / "66_PNEZD_CSV.csv").read_bytes(), "a.csv").points}
    for name in ("66_PENZD_CSV.csv", "66-1_r2_penzd_csv.csv"):
        f = read_survey((FIX / "66_PENZD_CSV.csv").read_bytes(), name)
        assert f.format == "PENZD_CSV"
        assert {p.name: (p.x, p.y) for p in f.points} == base
    assert read_survey((FIX / "66_PNEZ_TXT.txt").read_bytes(), "66_PNEZ_TXT.txt").format == "PNEZ_TXT"


def test_space_table_with_two_word_header_warns():
    raw = "№ Восток Север Уровень воды\n1-01 1472880.04 593722.99 1.5\n".encode()
    f = read_survey(raw, "s.txt")
    assert f.format == "TABLE"
    assert any("через пробелы" in w and "2" in w for w in f.warnings)
