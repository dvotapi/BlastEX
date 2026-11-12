"""Блок 66 «Жуков Камень» для тестов проекта МВ v2 (TASK-018, PR 2).

Скважины и заряжание — как в `tests/test_safety_design.py` (выгрузка SHOTPlus,
Порэмит 1А 1120 кг/м³, d = 144 мм, забойка 2,5 м, ПД по фикстуре формы),
контур со свободной поверхностью — `block66_contour.json` паспорта на
бурение, сетка — квадратная 3,7 м. Коэффициенты — лист «Реквизиты» формы v0.11.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from design.mass_blast import block_from_design
from design.mass_blast_context import BlockSource, ContextReferences, build_document_context_v2
from design.models import BlastDesign, BlockContour, Point3
from tests.test_safety_design import FORM, MATERIALS, SITE_SAFETY, block66_design

CONTOUR = Path(__file__).parent / "fixtures" / "drill_passport" / "block66_contour.json"
PATTERN = {"pattern": "square", "spacing_a_m": 3.7}


def design66(*, surface_ms: float = 25.0) -> BlastDesign:
    design = block66_design(surface_ms=surface_ms)
    shape = json.loads(CONTOUR.read_text(encoding="utf-8"))
    design.contour = BlockContour(
        vertices=[Point3(x, y, 0.0) for x, y in shape["vertices"]],
        free_faces=shape["free_faces"],
        name="66",
    )
    design.pattern_params = dict(PATTERN)
    return design


def payload66(**changes: Any) -> dict[str, Any]:
    """Payload проекта МВ v2 блока 66 по реквизитам формы (без ФИО — они не выдумываются)."""

    payload: dict[str, Any] = {
        "name": "Проект МВ 66-26",
        "site_code": "ZHK",
        "object_name": "Месторождение «Жуков Камень»",
        "blast_date": "2026-10-14",
        "blast_time": "13:00",
        "context_version": 2,
        "responsibilities": [
            {"role_code": "blast_manager", "employee_code": "E1", "employee_name": "Руководитель", "position_name": "руководитель взрывных работ", "account_email": "lead@example.test"},
            {"role_code": "explosives_supervisor", "employee_code": "E2", "employee_name": "Кладовщик", "position_name": "заведующий складом ВМ", "account_email": "store@example.test"},
        ],
        "personnel": [
            {"role_code": "senior_blaster", "position": "взрывник", "name": "Взрывник"},
            {"role_code": "escort", "position": "взрывник", "name": "Взрывник"},
            {"role_code": "mining_master", "position": "мастер горный", "name": "Мастер"},
            {"role_code": "energy", "position": "главный энергетик", "name": "Энергетик"},
            {"role_code": "notify", "position": "главный инженер", "name": "Инженер"},
            {"role_code": "talon_receiver", "position": "мастер горный", "name": "Мастер"},
            {"role_code": "charging_crew", "position": "машинист БУ", "name": "Бригада"},
        ],
        "guard_posts": [{"code": str(i), "location": f"пост {i}"} for i in range(1, 6)],
        "signal_plan": {"profile_code": "STANDARD"},
        "explosives": {
            "bit_mm": FORM["inputs"]["bit_mm"],
            "reaming_k": FORM["inputs"]["reaming_k"],
            "initiation": "НСИ, дистанционное взрывание при помощи УВИ(м)",
            "scheme": "поочерёдная короткозамедленная",
            "q_tp_kg_m3": FORM["inputs"]["q_tp_kg_m3"],
            "q_just": "требования к кондиции горной массы",
        },
        "schedule": {
            "station": "за пределами опасной зоны, согласно схеме",
            "shelter": "за пределами опасной зоны, согласно схеме",
            "charging_from": "2026-10-13",
            "charging_shift_from": "10:00",
            "charging_shift_to": "17:00",
        },
        "blocks": [],
    }
    payload.update(changes)
    return payload


def context66(design: BlastDesign | None = None, payload: dict[str, Any] | None = None, **reference: Any) -> dict[str, Any]:
    design = design or design66()
    block = block_from_design(design, code="66", horizon="410")
    data = payload or payload66()
    data = {**data, "blocks": data.get("blocks") or [block.to_dict()]}
    source = BlockSource(design=design, site_safety=SITE_SAFETY, rock={"hardness_f": 14}, materials=MATERIALS)
    references = ContextReferences(**reference)
    return build_document_context_v2(data, [block], [source], references)
