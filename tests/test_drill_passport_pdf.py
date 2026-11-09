"""PDF паспорта на бурение (TASK-015, PR 2): формат чисел и отрисовка."""
from __future__ import annotations

import re
import shutil
import subprocess
from copy import deepcopy
from datetime import date as _date
from pathlib import Path

import pytest

from design.reporting.drill import fmt
from design.reporting.drill.pdf import render_passport_pdf
from tests.drill_passport_context import PAYLOAD_V07, context66, with_holes

NBSP = " "


@pytest.mark.parametrize(
    ("value", "digits", "expected"),
    [
        (2280.5, 1, f"2{NBSP}280,5"),
        (29366.4, 0, f"29{NBSP}366"),
        (12.884, 2, "12,88"),
        (10.0, 1, "10,0"),
        (1234567.0, 0, f"1{NBSP}234{NBSP}567"),
        (-0.04, 1, "0,0"),
        (None, 1, "—"),
    ],
)
def test_num(value, digits, expected):
    assert fmt.num(value, digits) == expected


def test_trimmed_number():
    assert fmt.short(1.5) == "1,5"
    assert fmt.short(1.0) == "1"
    assert fmt.short(None) == "—"


def test_date():
    assert fmt.date("2026-10-06") == "06.10.2026"
    assert fmt.date("") == "—"
    assert fmt.date("06.10.2026") == "06.10.2026"


def test_range():
    assert fmt.num_range(10.0, 13.84) == "10,0 – 13,8"
    assert fmt.num_range(10.0, 10.0) == "10,0"
    assert fmt.num_range(None, None) == "—"


# --- отрисовка -------------------------------------------------------------

GOLDEN = Path(__file__).parent / "fixtures" / "drill_passport" / "golden"
GOLDEN_DPI = 50
# Доля пикселей, отличающихся по яркости больше чем на 32 из 255.
GOLDEN_THRESHOLD = 0.02


def _pages(pdf: bytes) -> int:
    return len(re.findall(rb"/Type /Page[^s]", pdf))


@pytest.fixture(scope="module")
def pdf66() -> bytes:
    return render_passport_pdf(context66(), revision_no=1)


def test_pdf_is_byte_stable(pdf66):
    again = render_passport_pdf(deepcopy(context66()), revision_no=1)
    assert pdf66.startswith(b"%PDF")
    assert again == pdf66


def test_pdf_has_no_generation_time(pdf66):
    stamps = re.findall(rb"/CreationDate \(D:(\d{4})", pdf66)
    assert stamps and all(int(year) < _date.today().year for year in stamps)


def test_pdf_page_count(pdf66):
    assert _pages(pdf66) == 4
    assert _pages(render_passport_pdf(with_holes(context66(), 201), revision_no=1)) == 6
    assert _pages(render_passport_pdf(with_holes(context66(), 401), revision_no=1)) == 6


def test_long_texts_keep_four_pages():
    payload = deepcopy(PAYLOAD_V07)
    long = "очень длинный текст поля паспорта " * 12
    for key in ("basis", "site_preparation", "stakeout", "drilling_order", "access_route", "adjacent_works"):
        payload[key] = long
    payload["agreed_by"]["name"] = "Ф" * 120
    payload["personnel"] = [{"name": "Иванов И. И.", "position": long[:120]} for _ in range(20)]
    context = context66(payload)
    context["passport"]["passport_no"] = "№" * 120
    assert _pages(render_passport_pdf(context, revision_no=1)) == 4


def test_markup_in_user_text_is_escaped():
    payload = deepcopy(PAYLOAD_V07)
    payload["compiled_by"]["name"] = "<b>Плаксин</b> & <font>"
    payload["basis"] = "<para>ТП</para>"
    assert _pages(render_passport_pdf(context66(payload), revision_no=1)) == 4


def test_revision_number_changes_only_title(pdf66):
    other = render_passport_pdf(context66(), revision_no=2)
    assert other != pdf66
    assert _pages(other) == 4


@pytest.mark.skipif(shutil.which("pdftoppm") is None, reason="нет pdftoppm (poppler)")
def test_pages_match_golden(pdf66, tmp_path):
    from PIL import Image, ImageChops

    source = tmp_path / "passport.pdf"
    source.write_bytes(pdf66)
    subprocess.run(
        ["pdftoppm", "-r", str(GOLDEN_DPI), "-gray", "-png", "-f", "1", "-l", "3", str(source), str(tmp_path / "page")],
        check=True,
    )
    for number in (1, 2, 3):
        actual = Image.open(tmp_path / f"page-{number}.png").convert("L")
        expected = Image.open(GOLDEN / f"page-{number}.png").convert("L")
        assert actual.size == expected.size
        diff = ImageChops.difference(actual, expected).point(lambda value: 255 if value > 32 else 0)
        share = diff.histogram()[255] / (diff.width * diff.height)
        assert share < GOLDEN_THRESHOLD, f"стр. {number}: отличается {share:.1%} пикселей"


def _page_scales(context) -> list[float]:
    """Во сколько раз ужата каждая страница (1.0 — не ужата)."""

    from reportlab.platypus import KeepInFrame

    scales: list[float] = []
    original = KeepInFrame.wrap

    def wrap(self, available_width, available_height):
        result = original(self, available_width, available_height)
        scales.append(getattr(self, "_scale", 1.0))
        return result

    KeepInFrame.wrap = wrap
    try:
        render_passport_pdf(context, revision_no=1)
    finally:
        KeepInFrame.wrap = original
    return scales


def test_block66_pages_are_not_shrunk():
    assert all(scale <= 1.0 for scale in _page_scales(context66()))


def test_longest_allowed_texts_stay_readable():
    payload = deepcopy(PAYLOAD_V07)
    for key in ("basis", "site_preparation", "stakeout", "drilling_order", "access_route",
                "power_lines", "adjacent_works", "acceptance"):
        payload[key] = "т" * 300
    payload["personnel"] = [{"name": "Ф" * 120, "position": "Д" * 120} for _ in range(20)]
    # Ужатие не больше чем на четверть: страница остаётся читаемой.
    assert max(_page_scales(context66(payload))) <= 1.25


@pytest.mark.parametrize("items", [[133] * 12, [250] * 6 + [16] * 6, [117] * 12], ids=["12x133", "6x250", "12x117"])
def test_longest_allowed_profile_stays_readable(items):
    """Самый длинный профиль справочника и самые длинные поля паспорта — стр. 2 ужата не больше чем на четверть."""

    payload = deepcopy(PAYLOAD_V07)
    for key in ("site_preparation", "stakeout", "drilling_order", "access_route", "power_lines",
                "adjacent_works", "acceptance"):
        payload[key] = "т " * 150
    words = "слово " * 200
    context = context66(payload)
    context["profile"] = {
        "code": "MAX", "safety_items": [words[:size] for size in items],
        "safety_basis": "О" * 200, "drilling_technology": words[:300],
    }
    assert max(_page_scales(context)) <= 1.25
