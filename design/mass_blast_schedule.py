"""Распорядок проведения массового взрыва (прил. 12 ФНП 494) как данные (TASK-018, PR 2, §3.3).

37 пунктов формы ВМ.09.03 v0.11 в том же порядке и с теми же
формулировками. Наименования и постоянные тексты пунктов — профиль
документов (`mass_blast_profiles`); пустой профиль — тексты формы
(`DEFAULT_SCHEDULE_TEXTS`). Значения проекта подставляются здесь:
время сигналов от времени взрыва (пп. 163, 421, 422), опасные зоны,
объекты в зоне, ответственные. Ничего не выдумывается: нет времени взрыва —
пункты со временем пустые и ошибка `blast_time_missing`; нет человека на
роли — пустая строка и предупреждение `personnel_missing`.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Mapping, Sequence

from design.safety import num

__all__ = [
    "DEFAULT_SCHEDULE_TEXTS",
    "DEFAULT_SIGNALS",
    "PERSONNEL_ROLES",
    "SCHEDULE_ROLE_CODES",
    "build_schedule",
    "shift_time",
]

# Роли распорядка (§5 TASK-018, решение В2): люди без учёток, один человек —
# на нескольких ролях. Ответственный руководитель — роль согласования
# `blast_manager` (#113), раздатчик по умолчанию — `explosives_supervisor`.
PERSONNEL_ROLES: dict[str, str] = {
    "senior_blaster": "Старший взрывник (заряжание, монтаж сети)",
    "escort": "Сопровождающий при подвозке ВМ",
    "mining_master": "Вывод людей и транспорта, охрана опасной зоны (заказчик)",
    "energy": "Отключение электроэнергии",
    "notify": "Оповещение соседних предприятий",
    "talon_receiver": "Получает талон-допуск (представитель заказчика)",
    "blaster": "Взрывник по наряд-путёвке",
    "storekeeper": "Заведующий складом ВМ (раздатчик)",
    "site_manager": "Руководитель участка (выписывает наряд-путёвку)",
    "charging_crew": "Бригада очистки и заряжания скважин (бригадир, рабочие)",
}
# Роли, без которых распорядок неполон (остальные нужны слоям дня взрыва).
SCHEDULE_ROLE_CODES = ("senior_blaster", "mining_master", "energy", "notify", "talon_receiver", "escort", "charging_crew")

DEFAULT_SIGNALS = {
    "warning": "один продолжительный",
    "combat": "два продолжительных",
    "clear": "три коротких",
}

# Пункт → (наименование, постоянный текст или None — значение проекта).
DEFAULT_SCHEDULE_TEXTS: dict[str, tuple[str, str | None]] = {
    "1": ("Дата взрыва", None),
    "2": ("Место взрыва", None),
    "3": ("Время взрыва (местное)", None),
    "4": ("Заряжание: с … по … (даты); смена с …; в день взрыва — до", None),
    "5": ("Количество ВВ на взрыв (по проекту)", None),
    "6": ("Количество взрываемых скважин", None),
    "7": ("Способ взрывания и ступени замедления", None),
    "9": ("Порядок заряжания скважин", None),
    "10": ("Порядок монтажа взрывной сети", None),
    "11": ("Место взрывной станции / укрытия", None),
    "12": ("Опасная зона (техрасчёт): люди / механизмы / здания", None),
    "13": ("Объекты в опасной зоне", None),
    "14": ("Мероприятия по защите охраняемых объектов", None),
    "15": ("Отвод оборудования (экскаваторы, станки и пр.) от ближайшей скважины", None),
    "16": ("Запретная зона при заряжании (п. 159)", "не менее 20 м от ближайшего заряда; ограждение, знаки"),
    "17": ("Схема расстановки постов охраны опасной зоны", "ситуационный план Г.5; посты — п. 35"),
    "19": ("Подвозка ВМ к месту взрыва", None),
    "20": ("Очистка скважин перед заряжанием / бригада", None),
    "36": ("Ответственные лица (пп. 8, 18, 21–28); с распорядком ознакомлены", None),
    "29": ("Сигналы (п. 163) и действия — по распоряжению ответственного руководителя массового взрыва", None),
    "29.1": ("Посты выставлены, люди, не занятые заряжанием, удалены за пределы запретной зоны", None),
    "29.2": ("Заряжание; сбор перед выходом", None),
    "29.3": ("Проверка сети (п. 417), доклады о заряжании, постах, выводе людей (п. 420)", None),
    "30": ("Боевой сигнал, взрыв", None),
    "31": ("Осмотр блока ответственным руководителем (п. 421)", None),
    "32": ("Отбой — после осмотра, по указанию ответственного руководителя", None),
    "33": (
        "Допуск людей — после рассеивания пылегазового облака, восстановления видимости и осмотра (п. 422)",
        None,
    ),
    "34": (
        "При обнаружении отказа",
        "по инструкции ВМ.10.01; ликвидация — по проекту ВМ.10.03; талон-допуск не выдаётся до ликвидации",
    ),
    "35": ("Посты охраны опасной зоны (расстановка — Г.5)", None),
    "37": (
        "С проектом и распорядком ознакомлены, о порядке работ и правилах безопасности проинструктированы (п. 416)",
        None,
    ),
}
FAMILIARIZATION_ROWS = 9
WARNING_BEFORE_MIN = 60
INSPECTION_AFTER_MIN = 15
ADMITTANCE_AFTER_MIN = 30


def _with_detail(duty: str, detail: str) -> str:
    """Обязанность с уточнением проекта («… — куда», «… — чем»); без уточнения — как прежде."""

    return f"{duty} — {detail}" if detail else duty


def shift_time(value: str, minutes: int) -> str:
    """«13:00» + минуты → «HH:MM» (через полночь — по кругу); пусто или не время — пусто."""

    text = str(value or "").strip()
    try:
        moment = datetime.strptime(text[:5], "%H:%M")
    except ValueError:
        return ""
    return (moment + timedelta(minutes=minutes)).strftime("%H:%M")


def _person(person: Mapping[str, Any] | None) -> str:
    if not person:
        return ""
    return " ".join(part for part in (str(person.get("position") or "").strip(), str(person.get("name") or "").strip()) if part)


def build_schedule(
    *,
    project: Mapping[str, Any],
    schedule: Mapping[str, Any],
    people: Mapping[str, Mapping[str, Any]],
    zones: Mapping[str, float | None],
    objects: Sequence[Mapping[str, Any]],
    blocks: Sequence[Mapping[str, Any]],
    totals: Mapping[str, Any],
    guard_posts: Sequence[Mapping[str, Any]],
    texts: Mapping[str, Any],
    signals: Mapping[str, str] | None = None,
    profile_texts: Mapping[str, Mapping[str, str]] | None = None,
) -> tuple[dict[str, Any], list[dict[str, str]]]:
    """Пункты распорядка и замечания.

    `people` — роль → {position, name} (включая `blast_manager`);
    `zones` — {people, mechanisms, buildings} проекта; `totals` — масса ВВ и
    ПД, кг, число скважин; `texts` — способ инициирования и интервалы.
    """

    issues: list[dict[str, str]] = []
    overrides = profile_texts or {}
    signal = {**DEFAULT_SIGNALS, **{key: value for key, value in (signals or {}).items() if value}}
    blast_time = str(project.get("blast_time") or "").strip()
    if not shift_time(blast_time, 0):
        issues.append(
            {
                "level": "error",
                "code": "blast_time_missing",
                "message": "Не задано время взрыва: в распорядке не будет времени сигналов, осмотра и допуска.",
                "path": "project.blast_time",
            }
        )
    warning_time = shift_time(blast_time, -WARNING_BEFORE_MIN)

    def title(point: str) -> str:
        own = str((overrides.get(point) or {}).get("title") or "").strip()
        return own or DEFAULT_SCHEDULE_TEXTS[point][0]

    def fixed(point: str) -> str:
        own = str((overrides.get(point) or {}).get("value") or "").strip()
        return own or str(DEFAULT_SCHEDULE_TEXTS[point][1] or "")

    def item(point: str, value: Any) -> dict[str, Any]:
        return {"point": point, "title": title(point), "value": value}

    # Куда выводятся люди и чем подаются сигналы — к строкам ответственных (пп. 21, 27).
    exit_route = str(schedule.get("exit_route") or "").strip()
    siren = str(schedule.get("siren") or "").strip()
    lead = _person(people.get("blast_manager"))
    master = _person(people.get("mining_master"))
    places = "; ".join(
        f"блок № {block.get('code', '')}, гор. {block.get('horizon', '')} м" for block in blocks
    )
    site = str(project.get("object_name") or "").strip()
    measures = [f"{obj['name']}: {obj['measures']}" for obj in objects if obj.get("position") == "В ЗОНЕ" and obj.get("measures")]
    inside = [str(obj["name"]) for obj in objects if obj.get("position") == "В ЗОНЕ"]
    station = str(schedule.get("station") or "").strip()
    shelter = str(schedule.get("shelter") or "").strip()
    if not station:
        issues.append(
            {
                "level": "error",
                "code": "blast_station_missing",
                "message": "Укажите место взрывной станции (п. 11 распорядка).",
                "path": "schedule.station",
            }
        )

    def zone(key: str) -> str:
        value = zones.get(key)
        return num(value) if value else "—"

    points = [
        item("1", str(project.get("blast_date") or "")),
        item("2", ", ".join(filter(None, [places, site]))),
        item("3", blast_time),
        item(
            "4",
            {
                "from_date": str(schedule.get("charging_from") or ""),
                "to_date": str(project.get("blast_date") or ""),
                "shift_from": str(schedule.get("charging_shift_from") or ""),
                "shift_to": str(schedule.get("charging_shift_to") or ""),
                "blast_day_until": warning_time,
            },
        ),
        item(
            "5",
            f"{num(float(totals.get('explosive_kg') or 0))} кг ({texts.get('explosives', '')}); "
            f"ПД — {num(float(totals.get('primer_kg') or 0))} кг",
        ),
        item("6", f"{int(totals.get('hole_count') or 0)} шт"),
        item("7", "; ".join(filter(None, [str(texts.get("initiation") or ""), str(texts.get("intervals") or "")])) + " (Г.4)"),
        item("9", str(schedule.get("charging_order") or "")),
        item("10", str(schedule.get("network_order") or "")),
        item("11", " / ".join(filter(None, [station, shelter]))),
        item("12", f"{zone('people')} / {zone('mechanisms')} / {zone('buildings')} м"),
        item("13", "; ".join(inside) if inside else "отсутствуют"),
        item("14", "; ".join(measures) or str(schedule.get("measures") or "") or ("не требуются" if not inside else "")),
        item("15", f"не менее {zone('mechanisms')} м; оставляемое в зоне — укрывается"),
        item("16", fixed("16")),
        item("17", fixed("17")),
        item("19", "; ".join(filter(None, [str(schedule.get("transport") or ""), f"сопровождает {_person(people.get('escort'))}" if people.get("escort") else ""]))),
        item("20", "; ".join(filter(None, [str(schedule.get("cleaning") or ""), _person(people.get("charging_crew"))]))),
        {"point": "", "title": "инструктаж бригады проведён", "value": str(schedule.get("briefing_date") or schedule.get("charging_from") or "")},
    ]

    responsibilities = [
        {"points": "18", "duty": "Ответственный руководитель массового взрыва", "who": lead},
        {"points": "8, 22", "duty": "Старший взрывник: заряжание и монтаж взрывной сети", "who": _person(people.get("senior_blaster"))},
        {"points": "21", "duty": _with_detail("Вывод людей из запретной и опасной зон", exit_route), "who": "; ".join(filter(None, [lead, master]))},
        {"points": "23, 25", "duty": "Вывод внутрикарьерного транспорта, отвод оборудования", "who": master},
        {"points": "24", "duty": "Охрана запретной / опасной зоны", "who": " / ".join(filter(None, [lead, master]))},
        {
            "points": "26",
            "duty": "Отключение электроэнергии, удаление аппаратуры; проверка и подключение после взрыва",
            "who": _person(people.get("energy")),
        },
        {"points": "27", "duty": _with_detail("Подача звуковых сигналов", siren), "who": "; ".join(filter(None, [lead, f"исполнитель — {master}" if master else ""]))},
        {
            "points": "28",
            "duty": "Оповещение соседних предприятий, органов местного самоуправления и населения",
            "who": _person(people.get("notify")),
        },
    ]
    gather = str(schedule.get("gather") or "").strip()
    senior = _person(people.get("senior_blaster"))
    signal_rows = [
        {"point": "29.1", "action": title("29.1"), "signal": f"предупредительный: {signal['warning']}", "time": warning_time, "not_earlier": False},
        {
            "point": "29.2",
            "action": "; ".join(filter(None, [f"Заряжание — {senior}" if senior else "Заряжание", f"сбор перед выходом — {gather}" if gather else ""])),
            "signal": "—",
            "time": "",
            "not_earlier": False,
        },
        {"point": "29.3", "action": title("29.3"), "signal": "—", "time": "", "not_earlier": False},
        {"point": "30", "action": title("30"), "signal": f"боевой: {signal['combat']}", "time": shift_time(blast_time, 0), "not_earlier": False},
        {"point": "31", "action": title("31"), "signal": "—", "time": shift_time(blast_time, INSPECTION_AFTER_MIN), "not_earlier": True},
        {"point": "32", "action": title("32"), "signal": f"отбой: {signal['clear']}", "time": "", "not_earlier": False},
        {"point": "33", "action": title("33"), "signal": "—", "time": shift_time(blast_time, ADMITTANCE_AFTER_MIN), "not_earlier": True},
    ]
    posts = [
        {
            "number": index + 1,
            "location": str(post.get("location") or "") or "по ситуационному плану Г.5",
            "posted_at": warning_time,
            "guard": "",
        }
        for index, post in enumerate(guard_posts)
    ]
    familiar: list[dict[str, str]] = []
    seen: set[str] = set()
    for role in ("blast_manager", "senior_blaster", "mining_master", "energy", "notify", "talon_receiver", "charging_crew"):
        person = people.get(role) or {}
        name = str(person.get("name") or "").strip()
        if name and name not in seen:
            seen.add(name)
            familiar.append({"name": name, "position": str(person.get("position") or "").strip()})
    familiar += [{"name": "", "position": ""} for _ in range(max(0, FAMILIARIZATION_ROWS - len(familiar)))]

    missing = [PERSONNEL_ROLES[role] for role in SCHEDULE_ROLE_CODES if not str((people.get(role) or {}).get("name") or "").strip()]
    if missing:
        issues.append(
            {
                "level": "warning",
                "code": "personnel_missing",
                "message": "В распорядке не заполнены роли: " + "; ".join(missing) + ". В документе останутся пустые строки.",
                "path": "personnel",
            }
        )

    return (
        {
            "points": points,
            "responsibilities": {"point": "36", "title": title("36"), "rows": responsibilities},
            "signals": {"point": "29", "title": title("29"), "rows": signal_rows},
            "refusal": item("34", fixed("34")),
            "posts": {"point": "35", "title": title("35"), "instructed_by": master, "rows": posts},
            "familiarization": {"point": "37", "title": title("37"), "rows": familiar},
        },
        issues,
    )
