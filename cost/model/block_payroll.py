"""ФОТ экипажа бурения блока по методике TASK-010 (решение владельца 25.10.2026).

По методике считается только экипаж операций бурения
(`labor.DRILLING_OPERATIONS`) — машинист и помощник; остальные прямые
должности остаются на ставках (`cost/model/labor.py`).

Раздел «экипаж». Состав берётся из бригады блока — вкладки, иначе шаблона
пакета (`labor.crew_members`), а не из всех сдельщиков организации: вторая
сдельная должность чужой операции или чужого станка долю в марже не завышает.
`crew_roster` — общее правило для явного состава: основная должность, которой
в нём нет, добавляется с одним человеком в смене и предупреждением, иначе её
премия молча выпала бы из доли в марже.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Sequence

from cost.model import labor
from cost.model.inputs import ModelContext, payload_text


@dataclass(frozen=True)
class CrewSlot:
    """Должность экипажа бурения на блоке."""

    position_code: str
    # Человек в смене; ноль в составе уже заменён одним человеком.
    headcount: Decimal
    # Ручная поправка смен на блок с вкладки; None — норматив.
    shifts_override: Decimal | None


def crew_roster(
    members: Sequence[tuple[str, Decimal]], main_code: str
) -> tuple[tuple[tuple[str, Decimal], ...], tuple[str, ...]]:
    """Явный состав экипажа с основной должностью.

    Нет основной должности — она ставится первой с одним человеком в смене,
    запрос не отклоняется (решение владельца 04.10.2026).
    """

    roster = tuple(members)
    if any(code == main_code for code, _ in roster):
        return roster, ()
    return (
        ((main_code, Decimal("1")), *roster),
        (
            "Основная должность добавлена в экипаж, один человек в смене: "
            "без неё её сдельная премия не вошла бы в долю в марже.",
        ),
    )


def block_crew(context: ModelContext) -> tuple[CrewSlot, ...]:
    """Экипаж бурения блока: прямые должности операций бурения пакета.

    Должность, которой нет в справочнике, пропускается молча: о ней
    предупреждает `labor.compute`.
    """

    slots: list[CrewSlot] = []
    for position_code, headcount, manual_shifts in labor.crew_members(context):
        position = context.item("positions", position_code)
        if position is None:
            continue
        if payload_text(position, "category", "DIRECT") != "DIRECT":
            continue
        operation_code = payload_text(position, "operation_code")
        if operation_code not in labor.DRILLING_OPERATIONS or not context.has_operation(operation_code):
            continue
        slots.append(CrewSlot(position_code, labor._per_shift_headcount(headcount), manual_shifts))
    return tuple(slots)
