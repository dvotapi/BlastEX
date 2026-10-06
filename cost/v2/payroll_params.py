"""Параметры ФОТ года (TASK-010): какая запись `payroll_params` действует.

Общая для методики ФОТ (`cost/model/payroll_inputs.py`) и сметы V1
(`cost/v2/legacy_adapter.py`): оба места должны брать один и тот же МРОТ.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from pydantic import ValidationError

from cost.v2.models import ReferenceItem
from cost.v2.schemas.payroll import PayrollParamsPayload

__all__ = ["PayrollParamsChoice", "payroll_params_for_year"]


@dataclass(frozen=True)
class PayrollParamsChoice:
    item: ReferenceItem
    params: PayrollParamsPayload
    # Пусто — взят запрошенный год; иначе пояснение, какой год взят вместо него.
    note: str = ""


def payroll_params_for_year(items: Iterable[ReferenceItem], year: int) -> PayrollParamsChoice | None:
    """Параметры запрошенного года, иначе ближайшего прошлого, иначе ближайшего будущего.

    Запись, которая не проходит схему, пропускается: публикация такую не
    пропустит, а снимок до TASK-010 раздела не содержит вовсе. None — ни одной
    годной записи.
    """

    valid: list[tuple[ReferenceItem, PayrollParamsPayload]] = []
    for item in items:
        if not item.is_active:
            continue
        try:
            valid.append((item, PayrollParamsPayload.model_validate(item.payload)))
        except ValidationError:
            continue
    if not valid:
        return None
    exact = next((pair for pair in valid if pair[1].year == year), None)
    if exact is not None:
        return PayrollParamsChoice(*exact)
    past = [pair for pair in valid if pair[1].year < year]
    item, params = (
        max(past, key=lambda pair: pair[1].year) if past else min(valid, key=lambda pair: pair[1].year)
    )
    return PayrollParamsChoice(item, params, f"Параметров ФОТ за {year} год нет — взяты за {params.year} год.")
