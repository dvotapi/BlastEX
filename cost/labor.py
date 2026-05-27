"""
Расчёт ФОТ производственного персонала (блок 2.3 сметы БВР).

Формула строки (Excel):
  ((объём × сдельная + оклад / смен_в_месяце) × ставки) / коэфф_«на_руки»
"""
from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass
class JobPosition:
    id: str
    name: str
    fixed_salary_monthly: float
    piece_rate_per_m3: float


@dataclass
class LaborAssignment:
    id: str
    position_id: str
    headcount: float
    volume_m3: float
    employee_shifts: float = 1.0


@dataclass
class LaborCostParts:
    fixed_part: float
    piece_part: float

    @property
    def subtotal(self) -> float:
        return self.fixed_part + self.piece_part


@dataclass
class LaborLineResult:
    assignment_id: str
    position_id: str
    position_name: str
    headcount: float
    volume_m3: float
    employee_shifts: float
    fixed_part: float
    piece_part: float
    line_amount: float


@dataclass
class LaborFOTSettings:
    shifts_per_month: float = 5.0
    net_to_gross_factor: float = 0.85
    accident_rate: float = 0.0042
    social_rate: float = 0.30
    vacation_reserve_divisor: float = 5.0


@dataclass
class LaborFOTResult:
    lines: list[LaborLineResult]
    gross_salary: float
    accident_contribution: float
    social_contribution: float
    vacation_reserve: float
    contributions_total: float
    total_fot: float
    settings: LaborFOTSettings

    @property
    def net_salary(self) -> float:
        return sum(line.line_amount for line in self.lines)


DEFAULT_LABOR_CATALOG: list[JobPosition] = [
    JobPosition("labor_master", "Руководитель взрывных работ (мастер БВР)", 80_000.0, 0.25),
    JobPosition("labor_blasters", "Взрывники", 55_000.0, 0.25),
    JobPosition("labor_driller", "Бурильщик", 55_000.0, 0.20),
    JobPosition("labor_assistant", "Помощник бурильщика", 35_000.0, 0.15),
    JobPosition("labor_miner", "Горнорабочий", 35_000.0, 0.15),
    JobPosition("labor_driver_szm", "Водитель СЗМ", 60_000.0, 0.30),
    JobPosition("labor_driver_del", "Водитель доставщика", 80_000.0, 0.30),
]


DEFAULT_LABOR_ASSIGNMENTS: list[LaborAssignment] = [
    LaborAssignment("la_1", "labor_master", 1.0, 30_000.0),
    LaborAssignment("la_2", "labor_blasters", 2.0, 30_000.0),
    LaborAssignment("la_3", "labor_driver_szm", 1.0, 27_219.0),
    LaborAssignment("la_4", "labor_driver_del", 1.0, 27_219.0),
]


def get_default_labor_catalog() -> list[JobPosition]:
    return list(DEFAULT_LABOR_CATALOG)


def get_default_labor_assignments() -> list[LaborAssignment]:
    return list(DEFAULT_LABOR_ASSIGNMENTS)


def labor_catalog_to_records(items: list[JobPosition]) -> list[dict]:
    return [asdict(item) for item in items]


def labor_catalog_from_records(records: list[dict]) -> list[JobPosition]:
    out: list[JobPosition] = []
    for row in records:
        out.append(
            JobPosition(
                id=str(row.get("id", "")),
                name=str(row.get("name", "")),
                fixed_salary_monthly=float(row.get("fixed_salary_monthly", 0) or 0),
                piece_rate_per_m3=float(row.get("piece_rate_per_m3", 0) or 0),
            )
        )
    return out


def labor_assignments_to_records(items: list[LaborAssignment]) -> list[dict]:
    return [asdict(item) for item in items]


def labor_assignments_from_records(records: list[dict]) -> list[LaborAssignment]:
    out: list[LaborAssignment] = []
    for row in records:
        out.append(
            LaborAssignment(
                id=str(row.get("id", "")),
                position_id=str(row.get("position_id", "")),
                headcount=float(row.get("headcount", 1) or 1),
                volume_m3=float(row.get("volume_m3", 0) or 0),
                employee_shifts=float(row.get("employee_shifts", 1) or 1),
            )
        )
    return out


def get_job_position(catalog: list[JobPosition], position_id: str) -> JobPosition | None:
    for item in catalog:
        if item.id == position_id:
            return item
    return None


def calculate_labor_cost(
    position_id: str,
    headcount: float,
    volume_m3: float,
    shifts_per_month: float,
    catalog: list[JobPosition],
    *,
    employee_shifts: float = 1.0,
) -> LaborCostParts:
    """
    fixed_part = (оклад / смен_в_месяце) × рабочие_смены_сотрудника
    piece_part = объём × сдельная_расценка
    """
    position = get_job_position(catalog, position_id)
    if position is None:
        return LaborCostParts(fixed_part=0.0, piece_part=0.0)

    if shifts_per_month <= 0:
        shifts_per_month = 1.0

    fixed_part = (position.fixed_salary_monthly / shifts_per_month) * employee_shifts
    piece_part = volume_m3 * position.piece_rate_per_m3
    return LaborCostParts(fixed_part=fixed_part, piece_part=piece_part)


def calculate_labor_line(
    assignment: LaborAssignment,
    catalog: list[JobPosition],
    settings: LaborFOTSettings,
) -> LaborLineResult | None:
    position = get_job_position(catalog, assignment.position_id)
    if position is None:
        return None

    parts = calculate_labor_cost(
        assignment.position_id,
        assignment.headcount,
        assignment.volume_m3,
        settings.shifts_per_month,
        catalog,
        employee_shifts=assignment.employee_shifts,
    )
    net_amount = parts.subtotal * assignment.headcount
    gross_amount = net_amount
    if 0 < settings.net_to_gross_factor < 1:
        gross_amount = net_amount / settings.net_to_gross_factor

    return LaborLineResult(
        assignment_id=assignment.id,
        position_id=assignment.position_id,
        position_name=position.name,
        headcount=assignment.headcount,
        volume_m3=assignment.volume_m3,
        employee_shifts=assignment.employee_shifts,
        fixed_part=parts.fixed_part,
        piece_part=parts.piece_part,
        line_amount=gross_amount,
    )


def calculate_labor_fot(
    *,
    catalog: list[JobPosition],
    assignments: list[LaborAssignment],
    settings: LaborFOTSettings | None = None,
) -> LaborFOTResult:
    settings = settings or LaborFOTSettings()
    lines: list[LaborLineResult] = []
    for assignment in assignments:
        line = calculate_labor_line(assignment, catalog, settings)
        if line is not None:
            lines.append(line)

    gross_salary = sum(line.line_amount for line in lines)
    accident = gross_salary * settings.accident_rate
    social = gross_salary * settings.social_rate
    vacation = (
        (gross_salary + accident + social) / settings.vacation_reserve_divisor
        if settings.vacation_reserve_divisor > 0
        else 0.0
    )
    contributions = accident + social + vacation
    total_fot = gross_salary + contributions

    return LaborFOTResult(
        lines=lines,
        gross_salary=gross_salary,
        accident_contribution=accident,
        social_contribution=social,
        vacation_reserve=vacation,
        contributions_total=contributions,
        total_fot=total_fot,
        settings=settings,
    )


def labor_table_rows(result: LaborFOTResult) -> list[dict]:
    rows: list[dict] = []
    for line in result.lines:
        rows.append({
            "Должность": line.position_name,
            "Ставки": line.headcount,
            "Объём, м³": round(line.volume_m3, 1),
            "Смены сотр.": line.employee_shifts,
            "Окладная часть, руб": round(line.fixed_part * line.headcount, 2),
            "Сдельная часть, руб": round(line.piece_part * line.headcount, 2),
            "ЗП на руки, руб": round(
                (line.fixed_part + line.piece_part) * line.headcount, 2
            ),
            "ЗП начисленная, руб": round(line.line_amount, 2),
        })
    return rows


def labor_summary_rows(result: LaborFOTResult) -> list[tuple[str, str]]:
    return [
        ("Итого заработная плата (начисленная)", f"{result.gross_salary:,.2f} руб"),
        ("Отчисления от несчастного случая", f"{result.accident_contribution:,.2f} руб"),
        ("Отчисления в фонды соц. страхования", f"{result.social_contribution:,.2f} руб"),
        ("Резерв отпусков", f"{result.vacation_reserve:,.2f} руб"),
        ("Итого отчисления", f"{result.contributions_total:,.2f} руб"),
        ("Итого ФОТ", f"{result.total_fot:,.2f} руб"),
    ]
