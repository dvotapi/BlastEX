"""Фикстура чертежа заказчика не раскрывает реальные координаты.

Репозиторий публичный, поэтому координаты блока 66 в МСК сдвинуты на
константу, которая в репозитории не записана. Любая координата фикстуры
(вершины, точки вставки и выравнивания подписей, центр вида, экстент)
должна лежать в локальном диапазоне: большое число — это или реальная
координата, или сама константа сдвига.
"""
from __future__ import annotations

from pathlib import Path

FIXTURE = Path(__file__).parent / "fixtures" / "cad" / "block66.dxf"
# Коды групп координат X/Y (10–18, 20–28) и их «вторых точек» (1010–1018 и т. п.).
COORDINATE_CODES = {*range(10, 19), *range(20, 29), *range(1010, 1019), *range(1020, 1029)}
LOCAL_LIMIT_M = 10_000.0


def _tags(text: str):
    lines = text.splitlines()
    for index in range(0, len(lines) - 1, 2):
        yield lines[index].strip(), lines[index + 1].strip()


def test_fixture_has_no_coordinates_outside_the_local_range():
    leaks = []
    for code, value in _tags(FIXTURE.read_text(encoding="utf-8")):
        if not code.isdigit() or int(code) not in COORDINATE_CODES:
            continue
        try:
            number = float(value)
        except ValueError:
            continue
        if abs(number) > LOCAL_LIMIT_M:
            leaks.append((code, value))

    assert leaks == []
