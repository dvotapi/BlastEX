"""Числа и даты паспорта по-русски: запятая, неразрывный пробел в тысячах."""
from __future__ import annotations

import re

DASH = "—"
NBSP = " "


def num(value: float | None, digits: int = 1) -> str:
    """«2 280,5»; None — «—»; минус у нуля не печатается."""

    if value is None:
        return DASH
    text = f"{float(value):,.{digits}f}"
    if float(text.replace(",", "")) == 0:
        text = text.lstrip("-")
    return text.replace(",", NBSP).replace(".", ",")


def short(value: float | None, digits: int = 2) -> str:
    """Без лишних нулей: «1,5», «1»."""

    if value is None:
        return DASH
    text = num(value, digits)
    return text.rstrip("0").rstrip(",") if "," in text else text


def num_range(low: float | None, high: float | None, digits: int = 1) -> str:
    """«10,0 – 13,8»; одинаковые концы — одно число."""

    if low is None or high is None:
        return DASH
    a, b = num(low, digits), num(high, digits)
    return a if a == b else f"{a} – {b}"


def date(value: str | None) -> str:
    """ISO «2026-10-06» → «06.10.2026»; другое — как есть, пусто — «—»."""

    text = (value or "").strip()
    match = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", text)
    if match:
        return f"{match[3]}.{match[2]}.{match[1]}"
    return text or DASH


def whole_degrees(value: float) -> int:
    """Угол в целых градусах, 0–359: азимут 359,6° — 0, как везде в документах."""

    return round(float(value)) % 360


def integer_number(text: str) -> int | None:
    """Номер скважины как число, если он записан числом без ведущих нулей («7»);
    «07», «1-01» — None: их пишут как есть, чтобы не терять знаки."""

    text = text.strip()
    if text.isascii() and text.isdigit() and text == str(int(text)):
        return int(text)
    return None
