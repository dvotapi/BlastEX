"""Фирменный стиль документов ООО «Комплексные решения» (ReportLab).

Общий для паспорта на бурение (TASK-015) и проекта массового взрыва
(TASK-018): шрифт Roboto, цвета, логотип COMPLEX и красная линия под шапкой.
Второго движка вёрстки нет — решение владельца 11.11.2026 (план TASK-018
PR 3, В1). Имена шрифтов и порядок рисования не менять: от них зависят байты
уже выпущенных PDF паспортов.
"""
from __future__ import annotations

from pathlib import Path

from reportlab.lib.colors import HexColor
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

# Ресурсы лежат в `drill/assets` с TASK-015: от пути к логотипу зависит имя
# картинки в PDF, а значит и байты выпущенных паспортов — не переносить.
ASSETS = Path(__file__).parent / "drill" / "assets"
LOGO = ASSETS / "logo.png"
FONT = "BlastEXRoboto"
FONT_BOLD = "BlastEXRoboto-Bold"

GRAPHITE = HexColor("#2E3237")
RED = HexColor("#B71C1C")
TINT = HexColor("#FCEDEE")
ZEBRA = HexColor("#F3F4F5")
LINE = HexColor("#C9CCD0")
GREY = HexColor("#6B7075")

ORGANIZATION = "ООО «Комплексные решения»"
LOGO_W = 34 * mm
LOGO_RATIO = 738 / 2400


FONT_FALLBACK = "BlastEXDejaVu"


def fallback_font_path() -> Path:
    """DejaVu Sans из пакета matplotlib (он в зависимостях): знаки, которых нет
    в Roboto (→, ∛, ⁴√, ⌈ ⌉). Системные шрифты не нужны."""

    import matplotlib

    return Path(matplotlib.get_data_path()) / "fonts" / "ttf" / "DejaVuSans.ttf"


def register_fallback_font() -> None:
    if FONT_FALLBACK not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont(FONT_FALLBACK, str(fallback_font_path())))


def register_fonts() -> None:
    if FONT not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont(FONT, str(ASSETS / "Roboto-Regular.ttf")))
        pdfmetrics.registerFont(TTFont(FONT_BOLD, str(ASSETS / "Roboto-Bold.ttf")))
        pdfmetrics.registerFontFamily(FONT, normal=FONT, bold=FONT_BOLD, italic=FONT, boldItalic=FONT_BOLD)


def fit_text(text: str, font: str, size: float, width: float) -> str:
    """Строка, обрезанная с «…» по ширине; помещается — как есть."""

    if pdfmetrics.stringWidth(text, font, size) <= width:
        return text
    while text and pdfmetrics.stringWidth(text + "…", font, size) > width:
        text = text[:-1]
    return text.rstrip() + "…"


def fit_font_size(text: str, font: str, size: float, width: float, min_size: float = 4.5) -> float:
    """Кегль, при котором строка помещается по ширине (не меньше `min_size`)."""

    actual = pdfmetrics.stringWidth(text, font, size)
    if actual <= width:
        return size
    return max(min_size, size * width / actual)


def draw_header(
    canvas, *, page_w: float, page_h: float, margin_x: float, header: str, title: str, logo_w: float = LOGO_W,
    logo=None, margin_right: float | None = None,
) -> None:
    """Логотип слева, красная линия; справа серым шапка (обрезается по ширине)
    и жирно название листа. Пустая шапка или название не рисуются.

    `page_h` — верхняя кромка шапки (у второго экземпляра талона — середина
    листа). `logo` — картинка логотипа; по умолчанию — путь к файлу, как у
    паспорта на бурение (от него зависят байты выпущенных паспортов)."""

    right = margin_x if margin_right is None else margin_right
    canvas.drawImage(logo if logo is not None else str(LOGO), margin_x, page_h - 17 * mm, width=logo_w,
                     height=logo_w * LOGO_RATIO, mask="auto")
    canvas.setStrokeColor(RED)
    canvas.setLineWidth(1.2)
    canvas.line(margin_x, page_h - 20 * mm, page_w - right, page_h - 20 * mm)
    if header:
        canvas.setFillColor(GREY)
        canvas.setFont(FONT, 7.5)
        header_w = page_w - margin_x - right - logo_w - 8 * mm
        canvas.drawRightString(page_w - right, page_h - 11.5 * mm, fit_text(header, FONT, 7.5, header_w))
    if title:
        canvas.setFillColor(GRAPHITE)
        canvas.setFont(FONT_BOLD, 8.5)
        canvas.drawRightString(page_w - right, page_h - 16.5 * mm, title)
