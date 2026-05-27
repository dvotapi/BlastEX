"""Шаблоны сценариев расчёта сметы (метаданные + подэтапы)."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

CostModule = str  # materials | drilling | labor | fixed | manufacturing

DEFAULT_SCENARIO_ID = "drill_blast"

# Режимы расчёта на вкладке «Расчёт»
CalcMode = str  # full_bvr | contour_bvr | drilling_geometry | manual
ExplosiveBasis = str  # per_m3 | per_m | none
ManualInputType = str  # pvv | evv | rc


@dataclass(frozen=True)
class ScenarioCalcProfile:
    """Какие блоки UI и расчёты нужны сценарию."""

    mode: CalcMode
    explosive_basis: ExplosiveBasis = "none"
    manual_type: ManualInputType = ""
    ui_caption: str = ""

    @property
    def needs_blast_optimization(self) -> bool:
        return self.mode in ("full_bvr", "contour_bvr")

    @property
    def needs_bvr_geometry(self) -> bool:
        return self.mode in ("full_bvr", "contour_bvr", "drilling_geometry")

    @property
    def needs_charge_design(self) -> bool:
        return self.mode in ("full_bvr", "contour_bvr")

    @property
    def is_manual_input(self) -> bool:
        return self.mode == "manual"


SCENARIO_CALC_PROFILES: dict[str, ScenarioCalcProfile] = {
    "drill_blast": ScenarioCalcProfile(
        mode="full_bvr",
        explosive_basis="per_m3",
        ui_caption="Комплекс БВР: оптимизация q, сетка, схема заряда и полная смета.",
    ),
    "blasting": ScenarioCalcProfile(
        mode="full_bvr",
        explosive_basis="per_m3",
        ui_caption="Взрывные работы: расчёт q и геометрии блока без затрат на бурение.",
    ),
    "contour_blasting": ScenarioCalcProfile(
        mode="contour_bvr",
        explosive_basis="per_m",
        ui_caption="Контурное взрывание: расход ВВ на погонный метр скважины.",
    ),
    "drilling": ScenarioCalcProfile(
        mode="drilling_geometry",
        explosive_basis="none",
        ui_caption="Буровые работы: сетка, глубина и погонаж без расчёта ВВ.",
    ),
    "pvv_delivery": ScenarioCalcProfile(
        mode="manual",
        manual_type="pvv",
        explosive_basis="none",
        ui_caption="Поставка ПВВ: масса ВВ и число скважин для логистики СЗМ и сметы.",
    ),
    "evv_manufacturing": ScenarioCalcProfile(
        mode="manual",
        manual_type="evv",
        explosive_basis="none",
        ui_caption="Производство ЭВВ: на вход — общая масса произведённой эмульсии.",
    ),
    "rc_drilling": ScenarioCalcProfile(
        mode="manual",
        manual_type="rc",
        explosive_basis="none",
        ui_caption="RC-бурение: геологоразведка, объём бурения без параметров БВР.",
    ),
}


def get_scenario_calc_profile(scenario_id: str) -> ScenarioCalcProfile:
    return SCENARIO_CALC_PROFILES.get(
        normalize_scenario_id(scenario_id),
        SCENARIO_CALC_PROFILES[DEFAULT_SCENARIO_ID],
    )

# Перенос сохранённых данных со старых id сценариев
LEGACY_SCENARIO_IDS: dict[str, str] = {
    "bvr_dry": "drill_blast",
    "bvr_wet": "drill_blast",
    "drilling_only": "drilling",
    "composite_ev_bvr": "drill_blast",
}


@dataclass
class ScenarioPhase:
    id: str
    name: str
    enabled: bool = True
    modules: list[CostModule] = field(default_factory=list)
    volume_source: str = "block_m3"  # block_m3 | footage_m | custom


@dataclass
class ScenarioTemplate:
    id: str
    name: str
    description: str
    phases: list[ScenarioPhase]

    def enabled_modules(self, overrides: dict[str, bool] | None = None) -> set[CostModule]:
        overrides = overrides or {}
        modules: set[CostModule] = set()
        for phase in self.phases:
            enabled = overrides.get(phase.id, phase.enabled)
            if enabled:
                modules.update(phase.modules)
        return modules

    def is_module_enabled(self, module: CostModule, overrides: dict[str, bool] | None = None) -> bool:
        return module in self.enabled_modules(overrides)


DEFAULT_SCENARIOS: list[ScenarioTemplate] = [
    ScenarioTemplate(
        id="evv_manufacturing",
        name="Производство компонентов ЭВВ",
        description="Изготовление компонентов эмульсионных ВВ на базе или пункте приготовления.",
        phases=[
            ScenarioPhase(
                id="evv_manufacturing",
                name="Производство компонентов ЭВВ",
                modules=["manufacturing", "labor", "fixed"],
                volume_source="custom",
            ),
        ],
    ),
    ScenarioTemplate(
        id="pvv_delivery",
        name="Поставка ПВВ в скважину",
        description="Заряжание скважин патронированными или гранулированными ВВ (ПВV/АСП).",
        phases=[
            ScenarioPhase(
                id="pvv_delivery",
                name="Поставка ПВВ в скважину",
                modules=["materials", "labor", "fixed"],
                volume_source="block_m3",
            ),
        ],
    ),
    ScenarioTemplate(
        id="blasting",
        name="Взрывные работы",
        description="Инициирование, взрывные работы и сопутствующие СИ без бурения и заряжания ВМ.",
        phases=[
            ScenarioPhase(
                id="blasting",
                name="Взрывные работы",
                modules=["materials", "labor", "fixed"],
                volume_source="block_m3",
            ),
        ],
    ),
    ScenarioTemplate(
        id="drilling",
        name="Буровые работы",
        description="Бурение скважин без заряжания и взрывания.",
        phases=[
            ScenarioPhase(
                id="drilling",
                name="Буровые работы",
                modules=["drilling", "labor", "fixed"],
                volume_source="footage_m",
            ),
        ],
    ),
    ScenarioTemplate(
        id="drill_blast",
        name="Буровзрывные работы",
        description="Комплекс: бурение, заряжание, взрывные работы на блоке.",
        phases=[
            ScenarioPhase(
                id="drill_blast",
                name="Буровзрывные работы",
                modules=["materials", "drilling", "labor", "fixed"],
                volume_source="block_m3",
            ),
        ],
    ),
    ScenarioTemplate(
        id="contour_blasting",
        name="Контурное взрывание",
        description="Бурение контурных скважин, заряжание и взрывание контура.",
        phases=[
            ScenarioPhase(
                id="contour_blasting",
                name="Контурное взрывание",
                modules=["drilling", "materials", "labor", "fixed"],
                volume_source="footage_m",
            ),
        ],
    ),
    ScenarioTemplate(
        id="rc_drilling",
        name="RC-бурение",
        description="Бурение методом обратной циркуляции (RC).",
        phases=[
            ScenarioPhase(
                id="rc_drilling",
                name="RC-бурение",
                modules=["drilling", "labor", "fixed"],
                volume_source="footage_m",
            ),
        ],
    ),
]

_SCENARIO_BY_ID = {scenario.id: scenario for scenario in DEFAULT_SCENARIOS}


def normalize_scenario_id(scenario_id: str) -> str:
    if scenario_id in _SCENARIO_BY_ID:
        return scenario_id
    return LEGACY_SCENARIO_IDS.get(scenario_id, DEFAULT_SCENARIO_ID)


def get_scenario_template(scenario_id: str) -> ScenarioTemplate | None:
    return _SCENARIO_BY_ID.get(normalize_scenario_id(scenario_id))


def list_scenario_templates() -> list[ScenarioTemplate]:
    return list(DEFAULT_SCENARIOS)


def scenario_template_to_dict(template: ScenarioTemplate) -> dict:
    return asdict(template)


def scenario_template_from_dict(data: dict) -> ScenarioTemplate:
    phases = [ScenarioPhase(**phase) for phase in data.get("phases", [])]
    return ScenarioTemplate(
        id=str(data["id"]),
        name=str(data["name"]),
        description=str(data.get("description", "")),
        phases=phases,
    )


def defaults_dir() -> Path:
    return Path(__file__).resolve().parent / "defaults" / "scenarios"


def export_default_scenario_templates() -> None:
    """Записать шаблоны сценариев в cost/defaults/scenarios/ (для репозитория)."""
    target = defaults_dir()
    target.mkdir(parents=True, exist_ok=True)
    valid_ids = {template.id for template in DEFAULT_SCENARIOS}
    for old_path in target.glob("*.json"):
        if old_path.stem not in valid_ids:
            old_path.unlink()
    for template in DEFAULT_SCENARIOS:
        path = target / f"{template.id}.json"
        path.write_text(
            json.dumps(scenario_template_to_dict(template), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


def load_scenario_template_from_repo(scenario_id: str) -> ScenarioTemplate | None:
    scenario_id = normalize_scenario_id(scenario_id)
    path = defaults_dir() / f"{scenario_id}.json"
    if not path.exists():
        return get_scenario_template(scenario_id)
    data = json.loads(path.read_text(encoding="utf-8"))
    return scenario_template_from_dict(data)
