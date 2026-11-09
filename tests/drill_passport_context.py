"""Снимок ревизии паспорта блока 66 со значениями эталона формы v0.7."""
from __future__ import annotations

from copy import deepcopy

from design.drilling_passport import passport_context
from tests.test_drilling_passport import _block66_design

SITE = {"bench_face_angle_deg": 75, "stable_slope_angle_deg": 65, "design_bench_height_m": 10}
RIG = {"axis_offset_m": 1.2}

PAYLOAD_V07 = {
    "agreed_by": {"position": "главный инженер", "organization": "ООО «Месторождение Жуков Камень»", "name": "Литун А.К."},
    "approved_by": {"position": "технический директор", "organization": "ООО «Комплексные решения»", "name": "Гизатуллин Р.Р."},
    "compiled_by": {"position": "инженер-проектировщик", "organization": "", "name": "Плаксин А.И."},
    "basis": "ТП ВМ.09.01 ред. [ ]; проект МВ № 66-26",
    "object_name": "Месторождение «Жуков Камень»",
    "customer": "ООО «Месторождение Жуков Камень»",
    "block": "66",
    "horizon": "+410,0",
    "block_area_m2": 2790,
    "rig_name": "JK830-2",
    "rig_number": "",
    "bit_diameter_mm": 140,
    "drilling_start": "2026-10-06",
    "drilling_end": "2026-10-12",
    "site_preparation": "бульдозером под руководством горного мастера заказчика; приём площадки по акту",
    "stakeout": "маркшейдерская служба заказчика по листу «Координаты скважин»",
    "drilling_order": "от бровки вглубь массива, рядами; 1-й ряд — первым, в светлое время суток",
    "access_route": "по съезду гор. 410, мачта в транспортном положении",
    "power_lines": "нет",
    "adjacent_works": "нет",
    "acceptance": "исполнительная съёмка маркшейдерской службой заказчика",
    "extra_approvals": ["маркшейдер [Фамилия И. О.]", "геолог [Фамилия И. О.]"],
    "tol_depth_m": 0.3,
    "tol_collar_m": 0.3,
    "personnel": [
        {"name": "[Фамилия И. О.]", "position": "горный мастер"},
        {"name": "Маланичев П.В.", "position": "машинист буровой установки"},
        {"name": "[Фамилия И. О.]", "position": "машинист буровой установки"},
        {"name": "[Фамилия И. О.]", "position": "маркшейдер"},
    ],
    "w_max_m": 6.0,
}

_CACHE: dict[str, dict] = {}


def context66(payload: dict | None = None) -> dict:
    """Снимок как у сервиса (`_context`): расчёт и блок `passport`."""

    if "base" not in _CACHE:
        _CACHE["base"] = passport_context(_block66_design(), PAYLOAD_V07, SITE, RIG)
    context = deepcopy(_CACHE["base"])
    context["passport"] = {
        "passport_no": "66-26/Б",
        "passport_date": "2026-10-05",
        "payload": deepcopy(payload if payload is not None else PAYLOAD_V07),
    }
    context["reference_revision_id"] = "ref-1"
    return context


def with_holes(context: dict, count: int) -> dict:
    """Тот же снимок с `count` скважинами (копии строк блока 66 с новыми номерами)."""

    source = context["holes"]
    holes = []
    for index in range(count):
        row = deepcopy(source[index % len(source)])
        row["number"] = str(index + 1)
        holes.append(row)
    result = deepcopy(context)
    result["holes"] = holes
    result["summary"]["hole_count"] = count
    result["summary"]["total_length_m"] = sum(row["length_m"] for row in holes)
    return result
