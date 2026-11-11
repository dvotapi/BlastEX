"""Раздел «Безопасные расстояния и выписка ВМ» (TASK-018, PR 1).

Коэффициенты расчёта безопасных расстояний по ФНП 494 (глава XII) на
объекте: одна запись на объект. Расчёт — `design/safety/`; таблицы K_з и K_н
— из п. 803, редактируются, если правила изменят. Запас ВМ для наряда-путёвки
в проект не входит — его подставит слой «наряд-путёвка».
"""
from __future__ import annotations

from decimal import Decimal

from pydantic import Field, field_validator, model_validator

from cost.v2.schemas.base import RefField, ReferencePayload, UnitField, field_error

__all__ = ["BlastSafetyPayload", "KnPoint", "KzPoint"]


class KzPoint(ReferencePayload):
    ratio: Decimal = UnitField("d", title="Отношение", description="Длина к диаметру скважины, в диаметрах")
    k: Decimal = UnitField("", title="Коэффициент", description="Значение коэффициента при этом отношении", gt=0, le=1)


class KnPoint(ReferencePayload):
    ratio: Decimal = UnitField(
        "", title="Отношение", description="Высота засыпки грунтом к высоте наружного заряда"
    )
    k: Decimal = UnitField("", title="Коэффициент", description="Значение коэффициента при этом отношении", gt=0, le=1)


# Таблицы п. 803 ФНП 494: (отношение, коэффициент).
KZ_STEMMING_ROWS = (("0", "1"), ("5", "0.15"), ("10", "0.02"), ("15", "0.003"), ("20", "0.002"))
KZ_FREE_ROWS = (("0", "1"), ("5", "0.3"), ("10", "0.07"), ("15", "0.02"), ("20", "0.004"))
KN_EXTERNAL_ROWS = (("0", "1"), ("1", "0.5"), ("2", "0.3"), ("3", "0.1"), ("4", "0.03"))
_TABLE_ROWS = {"kz_by_stemming": KZ_STEMMING_ROWS, "kz_by_free": KZ_FREE_ROWS, "kn_external": KN_EXTERNAL_ROWS}


def _points(rows: tuple[tuple[str, str], ...], model: type[ReferencePayload]) -> list:
    return [model(ratio=Decimal(ratio), k=Decimal(k)) for ratio, k in rows]


def _schema_default(rows: tuple[tuple[str, str], ...]) -> dict:
    """Строки таблицы умолчанием в JSON Schema: форма новой записи начинает с таблицы ФНП."""

    return {"default": [{"ratio": float(ratio), "k": float(k)} for ratio, k in rows]}


def _kz_stemming() -> list[KzPoint]:
    return _points(KZ_STEMMING_ROWS, KzPoint)


def _kz_free() -> list[KzPoint]:
    return _points(KZ_FREE_ROWS, KzPoint)


def _kn_external() -> list[KnPoint]:
    return _points(KN_EXTERNAL_ROWS, KnPoint)


class BlastSafetyPayload(ReferencePayload):
    site_code: str = RefField(
        "sites", title="Объект", description="Карьер, к которому относятся коэффициенты; одна запись на объект"
    )

    # Сейсмика, п. 792 ФНП 494.
    k_ground: Decimal = UnitField(
        "",
        title="K_г — грунт в основании охраняемых объектов",
        description=(
            "п. 792: скальные плотные — 5, скальные нарушенные — 8, песчаные и глинистые глубже 10 м — 12, "
            "обводнённые — 15, водонасыщенные — 20; при неясном грунте — ближайшее большее"
        ),
        default=Decimal("5"),
        gt=0,
    )
    k_structure: Decimal = UnitField(
        "",
        title="K_с — тип зданий и сооружений",
        description="п. 792: производственные с каркасом — 1, кирпичные до 2–3 этажей — 1,5, небольшие посёлки — 2",
        default=Decimal("2"),
        gt=0,
    )
    alpha_blast: Decimal = UnitField(
        "",
        title="α — условия взрывания",
        description="п. 792: рыхление — 1, выброс — 0,8, полууглублённый заряд — 0,5; в воде увеличить в 1,5–2 раза",
        default=Decimal("1"),
        gt=0,
    )
    buildings_damaged: bool = Field(
        default=False,
        title="Были повреждения зданий от взрывов",
        description="п. 795: без заключения экспертов сейсмически безопасное расстояние увеличивается вдвое",
    )

    # Разлёт, пп. 784–786 и прил. 21.
    people_min_m: Decimal = UnitField(
        "м",
        title="Минимум для людей, скважинные заряды рыхления",
        description="Прил. 21: не менее 200 м, на косогоре вниз по склону — не менее 300 м",
        default=Decimal("200"),
        ge=200,
    )
    k_mech: Decimal = UnitField(
        "доля",
        title="Доля зоны для механизмов",
        description="Принято проектом (п. 779 расстояние для механизмов не задаёт): доля опасной зоны для людей",
        default=Decimal("0.667"),
        gt=0,
        le=1,
    )
    relief_height_m: Decimal | None = UnitField(
        "м",
        title="Превышение блока над границей опасной зоны",
        description="п. 785: больше 30 м — зона разлёта вниз по склону увеличивается; пусто — рельеф не учтён",
        default=None,
    )
    slope_angle_deg: Decimal | None = UnitField(
        "°",
        title="Угол косогора",
        description="п. 785: взрыв на косогоре — зона разлёта вниз по склону увеличивается; пусто — не косогор",
        default=None,
        le=89,
    )

    # Ударная воздушная волна, пп. 803–807.
    rock_group_ix: bool = Field(
        default=False,
        title="Породы IX группы и выше",
        description="п. 804: радиус по действию воздушной волны на застекление ×1,5; группа у породы главнее",
    )
    rock_group_v_reduce: bool = Field(
        default=False,
        title="Уменьшать радиус для пород V группы и ниже",
        description="п. 804: радиус по действию воздушной волны можно уменьшить вдвое — только с обоснованием",
    )
    frost: bool = Field(
        default=False,
        title="Отрицательная температура воздуха",
        description="п. 807: радиус по действию воздушной волны на застекление ×1,5",
    )
    kz_by_stemming: list[KzPoint] = Field(
        default_factory=_kz_stemming,
        title="K_з по длине забойки",
        json_schema_extra=_schema_default(KZ_STEMMING_ROWS),
        description="п. 803: по отношению длины забойки к диаметру; берётся ближайшая меньшая точка",
    )
    kz_by_free: list[KzPoint] = Field(
        default_factory=_kz_free,
        title="K_з без забойки",
        json_schema_extra=_schema_default(KZ_FREE_ROWS),
        description="п. 803: по отношению свободной от заряда части скважины к диаметру",
    )
    kn_external: list[KnPoint] = Field(
        default_factory=_kn_external,
        title="K_н наружных зарядов",
        json_schema_extra=_schema_default(KN_EXTERNAL_ROWS),
        description="п. 803: по отношению высоты засыпки к высоте наружного заряда",
    )
    delay_group_ms: Decimal = UnitField(
        "мс",
        title="Порог группы замедления",
        description="п. 794: заряды с замедлением между ними меньше порога — один заряд при расчёте сейсмики",
        default=Decimal("20"),
        gt=0,
    )

    # Запас для наряда-путёвки: в проект не входит.
    reserve_primers_pcs: int = UnitField(
        "шт", title="Запас ПД", description="Подставляется в наряд-путёвку; в проект не входит", default=0
    )
    reserve_nsi_pcs: int = UnitField(
        "шт", title="Запас НСИ", description="Подставляется в наряд-путёвку; в проект не входит", default=0
    )
    reserve_starters_pcs: int = UnitField(
        "шт", title="Запас стартеров", description="Подставляется в наряд-путёвку; в проект не входит", default=0
    )

    @field_validator("kz_by_stemming", "kz_by_free", "kn_external", mode="before")
    @classmethod
    def _empty_table_is_standard(cls, value: object, info) -> object:
        """Пустая таблица — таблица п. 803 (форма пишет нетронутый список как `[]`)."""

        if value in (None, []):
            return [{"ratio": ratio, "k": k} for ratio, k in _TABLE_ROWS[info.field_name]]
        return value

    @model_validator(mode="after")
    def _consistent(self) -> "BlastSafetyPayload":
        if self.rock_group_ix and self.rock_group_v_reduce:
            field_error(
                type(self),
                "rock_group_v_reduce",
                "Породы IX группы и уменьшение для пород V группы взаимоисключающие",
                self.rock_group_v_reduce,
            )
        for name in ("kz_by_stemming", "kz_by_free", "kn_external"):
            rows = getattr(self, name)
            ratios = [row.ratio for row in rows]
            if min(ratios) != 0 or len(set(ratios)) != len(ratios):
                field_error(
                    type(self),
                    name,
                    "Таблица начинается с отношения 0 и не повторяет отношений",
                    len(rows),
                )
        return self
