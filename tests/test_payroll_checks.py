"""Проверки ревизии для методики ФОТ по нескольким разделам сразу (TASK-010 PR 1, Т15, Т16)."""
from __future__ import annotations

from decimal import Decimal

from cost.v2.models import ReferenceItem, finite_decimal
from cost.v2.payroll_checks import payroll_issues
from cost.v2.references import ValidationIssue, default_reference_sections, validate_reference_sections


def _item(code: str, payload: dict, name: str = "Запись") -> ReferenceItem:
    return ReferenceItem(code=code, name=name, payload=payload)


def _issues(**sections) -> list[ValidationIssue]:
    merged = dict(default_reference_sections())
    merged.update(sections)
    return validate_reference_sections(merged)


def _about(issues: list[ValidationIssue], section: str) -> list[tuple[str, str, str, str]]:
    return [(issue.level, issue.code, issue.field, issue.message) for issue in issues if issue.section == section]


PARAMS = {
    "year": "2026",
    "mrot": "27093",
    "annual_hours_40": "1972",
    "annual_hours_36": "1774.4",
    "work_days_year": "247",
    "holidays_year": "14",
}
CURVE = {
    "position_code": "POS_DRILLER",
    "scale_type": "CURVE_POWER",
    "norm_per_shift": "115.3846",
    "rate_norm": "45",
    "ceiling_per_shift": "184.6154",
    "rate_ceiling": "168.66",
}


def test_empty_new_sections_are_warnings_not_errors():
    issues = _issues()
    assert ("warning", "", "", "Не заведены параметры года: ФОТ по методике не рассчитается.") in _about(issues, "payroll_params")
    assert _about(issues, "drilling_difficulty") == [
        ("warning", "", "", "Не заведены коэффициенты сложности бурения: приведённые метры не посчитать.")
    ]
    assert _about(issues, "downtime_reasons") == [
        ("warning", "", "", "Не заведены причины простоев: простой не по вине машиниста не списать.")
    ]
    assert not [issue for issue in issues if issue.level == "error"]


def test_one_parameter_record_per_year():
    issues = _issues(payroll_params=(_item("P1", PARAMS), _item("P2", {**PARAMS, "year": 2026})))
    assert _about(issues, "payroll_params") == [
        ("error", "P2", "year", "Параметры 2026 года уже заведены записью P1.")
    ]


_FILLED_DIFFICULTY = {"hardness": [{"k": "1"}], "diameter": [{"diameter_mm": "152", "k": "1"}]}


def test_one_active_difficulty_record():
    issues = _issues(drilling_difficulty=(_item("DD1", _FILLED_DIFFICULTY), _item("DD2", _FILLED_DIFFICULTY)))
    assert _about(issues, "drilling_difficulty") == [
        ("error", "DD2", "", "Действует одна запись коэффициентов сложности бурения, уже есть DD1.")
    ]


# Codex к PR #83: раздел не должен считаться заведённым, если у действующей
# записи пусты (или не заполнены) таблицы крепости/диаметра — форма и схема
# допускают такую запись, а «приведённые метры» по ней не посчитать.


def test_active_difficulty_record_with_empty_tables_is_still_a_warning():
    issues = _issues(drilling_difficulty=(_item("DD", {"hardness": [], "diameter": []}),))
    assert _about(issues, "drilling_difficulty") == [
        ("warning", "", "", "Не заведены коэффициенты сложности бурения: приведённые метры не посчитать.")
    ]


def test_active_difficulty_record_with_both_tables_filled_is_not_a_warning():
    issues = _issues(drilling_difficulty=(_item("DD", _FILLED_DIFFICULTY),))
    assert _about(issues, "drilling_difficulty") == []


def test_active_difficulty_record_with_empty_diameter_table_is_a_warning():
    partial = {**_FILLED_DIFFICULTY, "diameter": []}
    issues = _issues(drilling_difficulty=(_item("DD", partial),))
    assert _about(issues, "drilling_difficulty") == [
        ("warning", "", "", "Не заведены коэффициенты сложности бурения: приведённые метры не посчитать.")
    ]


def _bits(material: dict, diameters: list[str]) -> dict:
    return {
        "materials": (_item("MAT_BIT", material, name="Коронка 165"),),
        "equipment_types": (_item("RIG", {"kind": "DRILL_RIG"}),),
        "drilling_conditions": (_item("COND", {"equipment_type_code": "RIG", "bit_material_code": "MAT_BIT"}),),
        "drilling_difficulty": (
            _item(
                "DD",
                {
                    "hardness": [{"k": "1"}],
                    "diameter": [{"diameter_mm": value, "k": "1"} for value in diameters],
                },
            ),
        ),
    }


def test_every_bit_diameter_needs_a_factor():
    issues = _issues(**_bits({"diameter_mm": "165"}, ["152"]))
    assert _about(issues, "drilling_difficulty") == [
        ("error", "DD", "diameter", "Нет коэффициента для коронки Ø 165 мм (Коронка 165).")
    ]
    assert _about(_issues(**_bits({"diameter_mm": "165.0"}, ["152", "165"])), "drilling_difficulty") == []


def test_bit_without_a_diameter_is_a_warning_on_the_material():
    issues = _issues(**_bits({}, ["152"]))
    assert _about(issues, "materials") == [
        (
            "warning",
            "MAT_BIT",
            "diameter_mm",
            "У коронки из условий бурения не задан диаметр: коэффициент диаметра для неё не проверен.",
        )
    ]


def test_bit_diameters_are_not_checked_while_the_section_is_empty():
    sections = _bits({"diameter_mm": "165"}, [])
    sections["drilling_difficulty"] = ()
    assert [issue for issue in _issues(**sections) if issue.level == "error"] == []


def _drilling_rate(**conditions) -> dict:
    return {
        "positions": (_item("POS_DRILLER", {"category": "INDIRECT", "difficulty": "NORMALIZED_METERS"}),),
        "labor_rates": (_item("RATE_DRILLER", CURVE),),
        "equipment_types": (_item("RIG", {"kind": "DRILL_RIG"}),),
        "drilling_conditions": tuple(
            _item(code, {"equipment_type_code": "RIG", **payload}) for code, payload in conditions.items()
        ),
    }


def test_ceiling_above_what_a_rig_drills_in_a_shift_is_a_warning():
    # Базовая строка 10 м/ч × (11 − 1) ч = 100 м/смену; строка по породе в сравнение не входит.
    issues = _issues(
        **_drilling_rate(
            COND_BASE={"tech_speed_m_per_h": "10", "unproductive_h_per_shift": "1"},
            COND_GRANITE={"rock_code": "ROCK", "tech_speed_m_per_h": "30"},
        ),
        rocks=(_item("ROCK", {}),),
    )
    assert _about(issues, "labor_rates") == [
        (
            "warning",
            "RATE_DRILLER",
            "ceiling_per_shift",
            "Потолок 184.6154 м/смену выше производительности станков по базовым условиям бурения "
            "(до 100 м/смену): машинист не дойдёт до потолка.",
        )
    ]


def test_ceiling_within_rig_capacity_passes():
    # 20 м/ч × 10 ч = 200 м/смену.
    issues = _issues(**_drilling_rate(COND_BASE={"tech_speed_m_per_h": "20", "unproductive_h_per_shift": "1"}))
    assert _about(issues, "labor_rates") == []


def test_rotation_maintenance_against_rig_maintenance_ratio():
    rig = (_item("RIG", {"kind": "DRILL_RIG", "maintenance_ratio": "0.14"}, name="JK830"),)
    # 15 × 0,14 / 1,14 = 1,84 смены: 2 в пределах полусмены, 3 — нет.
    assert _about(_issues(equipment_types=rig, sites=(_item("S", {}),)), "sites") == []
    issues = _issues(equipment_types=rig, sites=(_item("S", {"maintenance_shifts": "3"}),))
    assert _about(issues, "sites") == [
        (
            "warning",
            "S",
            "maintenance_shifts",
            "Плановое ТОиР 3 см за вахту расходится с долей ТОиР станка JK830: "
            "0.14 смены ТОиР на рабочую смену дают 1.84 см из 15.",
        )
    ]


def test_hazardous_class_needs_an_extra_tariff():
    position = (_item("POS_X", {"category": "INDIRECT", "work_conditions_class": "3.3"}),)
    issues = _issues(positions=position)
    assert _about(issues, "positions") == [
        (
            "warning",
            "POS_X",
            "work_conditions_class",
            "Для класса условий труда 3.3 в «Ставках и надбавках организации» не задан доп. тариф взносов: "
            "расчёт ФОТ возьмёт 0.",
        )
    ]
    sections = dict(default_reference_sections())
    rates = sections["organization_rates"][0]
    covered = ReferenceItem(
        code=rates.code,
        name=rates.name,
        payload={**rates.payload, "extra_tariffs": [{"work_conditions_class": "3.3", "rate": "0.06"}]},
    )
    assert _about(_issues(positions=position, organization_rates=(covered,)), "positions") == []
    assert _about(_issues(positions=(_item("POS_Y", {"category": "INDIRECT", "work_conditions_class": "2"}),)), "positions") == []


def test_extra_tariff_with_a_zero_rate_does_not_cover_the_class():
    # Форма подставляет 0 в новую строку доп. тарифа: строка есть, но класс
    # ещё не покрыт, пока ставка не больше нуля.
    position = (_item("POS_Z", {"category": "INDIRECT", "work_conditions_class": "3.2"}),)
    sections = dict(default_reference_sections())
    rates = sections["organization_rates"][0]
    zero_rate = ReferenceItem(
        code=rates.code,
        name=rates.name,
        payload={**rates.payload, "extra_tariffs": [{"work_conditions_class": "3.2", "rate": "0"}]},
    )
    issues = _issues(positions=position, organization_rates=(zero_rate,))
    assert _about(issues, "positions") == [
        (
            "warning",
            "POS_Z",
            "work_conditions_class",
            "Для класса условий труда 3.2 в «Ставках и надбавках организации» не задан доп. тариф взносов: "
            "расчёт ФОТ возьмёт 0.",
        )
    ]

    real_rate = ReferenceItem(
        code=rates.code,
        name=rates.name,
        payload={**rates.payload, "extra_tariffs": [{"work_conditions_class": "3.2", "rate": "0.04"}]},
    )
    assert _about(_issues(positions=position, organization_rates=(real_rate,)), "positions") == []


def test_schema_errors_inside_lists_carry_the_row_path():
    issues = _issues(
        positions=(_item("POS_DRILLER", {"category": "INDIRECT"}),),
        labor_rates=(
            _item(
                "RATE_STEP",
                {
                    "position_code": "POS_DRILLER",
                    "scale_type": "STEP",
                    "tiers": [{"upto_per_shift": "115", "rate": "45"}, {"upto_per_shift": "138", "rate": "40"}, {"rate": "140"}],
                },
            ),
        ),
    )
    assert _about(issues, "labor_rates") == [
        ("error", "RATE_STEP", "tiers.1.rate", "Расценка ступени не может быть ниже предыдущей")
    ]


# Регресс: битые значения в payload не должны ронять validate_reference_sections
# исключением — они уже отражены как ошибка схемы, а перекрёстные проверки
# просто не учитывают такое значение (Fix round 1).


def _schema_error_fields(issues: list[ValidationIssue], section: str) -> set[tuple[str, str, str]]:
    return {(issue.level, issue.code, issue.field) for issue in issues if issue.section == section}


def test_nan_ceiling_per_shift_does_not_crash_validation():
    # Нужна валидная базовая строка бурения, иначе `_ceiling_above_rigs` выходит
    # раньше сравнения "ceiling <= best" и баг не воспроизводится.
    sections = _drilling_rate(COND_BASE={"tech_speed_m_per_h": "20", "unproductive_h_per_shift": "1"})
    sections["labor_rates"] = (_item("RATE_DRILLER", {**CURVE, "ceiling_per_shift": "NaN"}),)
    issues = _issues(**sections)
    assert ("error", "RATE_DRILLER", "ceiling_per_shift") in _schema_error_fields(issues, "labor_rates")


def test_nan_tech_speed_does_not_crash_validation():
    # Нужны две базовые строки бурения, иначе `max()` над одним элементом не
    # сравнивает его ни с чем и баг не воспроизводится.
    issues = _issues(
        equipment_types=(_item("RIG", {"kind": "DRILL_RIG"}),),
        drilling_conditions=(
            _item("COND_OK", {"equipment_type_code": "RIG", "tech_speed_m_per_h": "20"}),
            _item("COND_NAN", {"equipment_type_code": "RIG", "tech_speed_m_per_h": "NaN"}),
        ),
    )
    assert ("error", "COND_NAN", "tech_speed_m_per_h") in _schema_error_fields(issues, "drilling_conditions")


def test_nan_maintenance_shifts_does_not_crash_validation():
    rig = (_item("RIG", {"kind": "DRILL_RIG", "maintenance_ratio": "0.14"}),)
    issues = _issues(equipment_types=rig, sites=(_item("S", {"maintenance_shifts": "NaN"}),))
    assert ("error", "S", "maintenance_shifts") in _schema_error_fields(issues, "sites")


def test_huge_rotation_does_not_crash_validation():
    # 1e30 × 0,14 / 1,14 не укладывается в 28 знаков Decimal при округлении до сотых.
    rig = (_item("RIG", {"kind": "DRILL_RIG", "maintenance_ratio": "0.14"}),)
    issues = _issues(equipment_types=rig, sites=(_item("S", {"shift_days_on": "1e30"}),))
    assert ("error", "S", "shift_days_on") in _schema_error_fields(issues, "sites")


def test_maintenance_check_skips_a_rotation_it_cannot_compute():
    # Минуя схему: пара пропускается без предупреждения, а не роняет проверку.
    rig = (_item("RIG", {"kind": "DRILL_RIG", "maintenance_ratio": "0.14"}),)
    issues = payroll_issues({"equipment_types": rig, "sites": (_item("S", {"shift_days_on": "1e30"}),)})
    assert [issue for issue in issues if issue.section == "sites"] == []


def test_non_list_diameter_does_not_crash_validation():
    issues = _issues(drilling_difficulty=(_item("DD", {"diameter": 5}),))
    assert ("error", "DD", "diameter") in _schema_error_fields(issues, "drilling_difficulty")


def test_non_list_extra_tariffs_does_not_crash_validation():
    sections = dict(default_reference_sections())
    rates = sections["organization_rates"][0]
    broken = ReferenceItem(
        code=rates.code, name=rates.name, payload={**rates.payload, "extra_tariffs": 5}
    )
    issues = _issues(organization_rates=(broken,))
    assert ("error", rates.code, "extra_tariffs") in _schema_error_fields(issues, "organization_rates")


# Codex к PR #83: числа немыслимого порядка (`"1e999999"`) схема не отвергает
# (сравнение с границей поля само по себе не переполняется), а дальнейшая
# арифметика (`_ceiling_above_rigs`, `_bit_diameters` + `_plain`) — падает.
# `finite_decimal` теперь отсекает такие значения по порядку числа.


def test_finite_decimal_rejects_numbers_outside_the_reference_range():
    assert finite_decimal("1e16") is None
    assert finite_decimal("1e-16") is None


def test_finite_decimal_keeps_numbers_within_the_reference_range():
    assert finite_decimal("1e15") == Decimal("1e15")
    assert finite_decimal("0") == Decimal("0")
    assert finite_decimal("0.001") == Decimal("0.001")


def test_unthinkably_huge_tech_speed_does_not_crash_validation():
    # До фикса: speed × (shift_hours − unproductive) бросает decimal.Overflow.
    issues = _issues(
        **_drilling_rate(COND_BASE={"tech_speed_m_per_h": "1e999999", "unproductive_h_per_shift": "1"})
    )
    assert all(len(issue.message) < 300 for issue in issues)


def test_unthinkably_huge_bit_diameter_does_not_crash_validation():
    # До фикса: `_plain` вызывает `.normalize()` на диаметре и бросает
    # decimal.Overflow при формировании сообщения об ошибке.
    issues = _issues(**_bits({"diameter_mm": "1e999999999999999999"}, ["152"]))
    assert all(len(issue.message) < 300 for issue in issues)
