"""Профиль паспорта на бурение (TASK-015, PR 2): тексты, которые печатает паспорт.

Меры безопасности и технология бурения у карьеров разные, поэтому это данные
справочника, а не код. Пустое поле — текст формы v0.7 по умолчанию
(`design/drilling_passport.py`); в ревизию паспорта тексты попадают копией.
"""
from __future__ import annotations

from pydantic import Field, model_validator

from cost.v2.schemas.base import ReferencePayload

__all__ = ["DrillPassportProfilePayload", "SafetyItem"]

# Пределы держат страницу 2 читаемой: с самыми длинными полями паспорта она
# ужимается не больше чем на четверть (тест `test_longest_allowed_profile_stays_readable`).
MAX_SAFETY_ITEMS = 12
MAX_SAFETY_ITEM_CHARS = 250
MAX_SAFETY_TOTAL_CHARS = 1600


class SafetyItem(ReferencePayload):
    text: str = Field(title="Пункт", description="Текст пункта мер безопасности", min_length=1, max_length=MAX_SAFETY_ITEM_CHARS)


class DrillPassportProfilePayload(ReferencePayload):
    safety_items: list[SafetyItem] = Field(
        default_factory=list,
        title="Основные меры безопасности",
        description="Пункты по порядку; пусто — 10 пунктов формы по умолчанию",
        max_length=MAX_SAFETY_ITEMS,
    )
    safety_basis: str = Field(
        default="",
        title="Основание",
        description="Строка под мерами безопасности; пусто — «Основание: ФНП 505 пп. 989–991, 993; ФНП 494 п. 187.»",
        max_length=200,
    )
    drilling_technology: str = Field(
        default="",
        title="Технология бурения",
        description="Текст строки «Технология бурения» на странице параметров; пусто — текст формы по умолчанию",
        max_length=300,
    )

    @model_validator(mode="after")
    def _total_length(self) -> "DrillPassportProfilePayload":
        total = sum(len(item.text) for item in self.safety_items)
        if total > MAX_SAFETY_TOTAL_CHARS:
            raise ValueError(
                f"Меры безопасности вместе — не длиннее {MAX_SAFETY_TOTAL_CHARS} символов (сейчас {total}): "
                "иначе страница паспорта станет нечитаемой"
            )
        return self
