"""Профиль файла выноса скважин для GNSS-приёмника (TASK-015, PR 5, спека §5).

Формат файла у контроллеров разный, поэтому это данные справочника, а не
код. Встроенные профили (`PNEZD_CSV`, `PENZD_CSV`, `PNEZ_TXT`, `DXF_POINTS`)
есть всегда — `design/export_survey.py`; запись справочника добавляет свой
профиль или с тем же кодом меняет встроенный. В ревизию паспорта профили
попадают копией.
"""
from __future__ import annotations

from typing import Literal

from pydantic import Field

from cost.v2.schemas.base import ReferencePayload

__all__ = ["StakeoutFormat", "StakeoutProfilePayload"]

StakeoutFormat = Literal["PNEZD_CSV", "PENZD_CSV", "PNEZ_TXT", "DXF_POINTS"]


class StakeoutProfilePayload(ReferencePayload):
    format: StakeoutFormat = Field(
        default="PNEZD_CSV",
        title="Формат",
        description=(
            "Порядок полей файла для приёмника; север раньше востока подходит Trimble Access, Carlson, "
            "South / Stonex, Emlid Flow и CHC LandStar"
        ),
    )
    header: bool = Field(default=False, title="Строка заголовка", description="Первой строкой — названия полей")
    elevation: bool = Field(
        default=True, title="Отметка устья", description="Выключено — поле отметки пустое (высоту не выносят)"
    )
    include_toe: bool = Field(
        default=False,
        title="Точки забоя наклонных",
        description="Следом за устьем наклонной скважины — точка её забоя",
    )
