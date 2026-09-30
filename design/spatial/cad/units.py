"""Единицы чертежа.

`$INSUNITS` в чертежах маркшейдеров ненадёжен: шаблон acadiso ставит
миллиметры, а координаты в МСК при этом в метрах (так у блока 66 и обоих
файлов блока 63). Поэтому масштаб решает размер чертежа, а `$INSUNITS` только
поясняет: сторона больше 20 км для блока и карьера неправдоподобна —
это миллиметры, и пользователю предлагается масштаб 0,001.
"""
from __future__ import annotations

from design.spatial.cad.model import CadWarning, ru_number

MILLIMETRE_SCALE = 0.001
# Сторона экстента, начиная с которой чертёж считаем миллиметровым.
MILLIMETRE_EXTENT = 20_000.0

INSUNITS_NAMES: dict[int, str] = {
    1: "дюймы",
    2: "футы",
    4: "миллиметры",
    5: "сантиметры",
    6: "метры",
    7: "километры",
    14: "дециметры",
}
METRES = 6


def detect_units(
    insunits: int | None, extent: tuple[float, float, float, float] | None
) -> tuple[float | None, list[CadWarning]]:
    """Предложенный масштаб (или None) и пояснения к единицам."""

    size = 0.0
    if extent is not None:
        xmin, ymin, xmax, ymax = extent
        size = max(xmax - xmin, ymax - ymin)

    if size > MILLIMETRE_EXTENT:
        return MILLIMETRE_SCALE, [
            CadWarning(
                code="units_mm",
                message=(
                    f"Чертёж размером {ru_number(size / 1000, 1)} км — похоже, он в миллиметрах. "
                    "Примените масштаб 0,001, чтобы перевести его в метры."
                ),
            )
        ]
    if insunits in (None, 0):
        return None, [
            CadWarning(code="units_missing", message="Единицы в файле не указаны — читаем в метрах.", level="info")
        ]
    if insunits != METRES:
        name = INSUNITS_NAMES.get(insunits, f"код {insunits}")
        return None, [
            CadWarning(
                code="units_declared",
                message=f"В файле указаны единицы «{name}», но размеры похожи на метры — читаем в метрах.",
                level="info",
            )
        ]
    return None, []
