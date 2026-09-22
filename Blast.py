import math  # Импортируем модуль математики (нужен для ПИ и возведения в степень)
from dataclasses import dataclass, replace  # Структуры данных и копия с изменённым полем

from simulation.fragmentation import cunningham as kr
from simulation.fragmentation.distributions import (
    rosin_rammler_characteristic_mm,
    rosin_rammler_oversize_pct,
)
from simulation.fragmentation.kuznetsov import kuznetsov_x50_mm, rock_factor_A
from simulation.fragmentation.kuzram import cunningham_uniformity_n
from simulation.fragmentation.units import relative_weight_strength

# --- БЛОК ОПИСАНИЯ ДАННЫХ Классов ---

@dataclass  # Специальная пометка: этот класс нужен только для хранения данных
class RockProperties:
    name: str           # Текстовое название породы (например, "Гранит")
    density_t_m3: float # Плотность породы в тоннах на кубометр
    ucs_mpa: float      # Предел прочности на сжатие в МПа
    fissuring_ff: float # Количество трещин на 1 метр массива (трещиноватость)

@dataclass
class ExplosiveProperties:
    name: str                     # Название взрывчатки (например, "ЭВЕРСИН-100")
    density_t_m3: float           # Плотность заряжания (г/см³ или т/м³)
    power_mj_kg: float            # Теплота взрыва Q_exp (МДж/кг). RE_weight = Q_exp/4,184 — сила ВВ относительно тротила

@dataclass
class TargetParams:
    lump_size_mm: float # Кондиционный размер куска, который мы считаем негабаритом (мм)
    hole_diameter_mm: float # Диаметр скважины (коронки) в миллиметрах
    overdrill_m: float = 1.0          # Фиксированный перебур в метрах
    hole_oversize_coeff: float = 1.05     # Коэффициент разбуривания (увеличение диаметра скважины относительно диаметра коронки)
    spacing_coeff_m: float = 1.25 # Коэффициент сетки (на сколько "а" больше чем "W")
    bench_height_m: float = 10.0 # Высота уступа в карьере в метрах

# Доступные диаметры буровых коронок, мм
CROWNS_MM = [110, 115, 122, 125, 130, 140, 152, 165, 171, 220, 250]

# Доля скважины, занятая зарядом (как в смете).
FILL_RATIO = 0.8


def _legacy_uniformity_raw(burden_m: float, diameter_m: float, spacing_to_burden: float) -> float:
    """Нераскэмпленный индекс равномерности n для расчёта «до исправления».

    Выражение должно оставаться идентичным нераскэмпленной части внутри
    simulation/fragmentation/kuzram.py::cunningham_uniformity_n (при
    drill_deviation_m = 0) — так расчёт «до исправления» и клэмпнутое n,
    которое он же использует для самого прогноза, не расходятся незаметно
    при будущей правке одной из формул. Результат может быть отрицательным
    или сколь угодно большим — здесь его никто не клэмпит.
    """
    return (2.2 - 14.0 * (burden_m / diameter_m)) * (1.0 + (spacing_to_burden - 1.0) / 2.0)


@dataclass(frozen=True)
class BlastPoint:
    """Расчёт одной коронки при заданном q — все промежуточные величины без округления."""

    q_kg_m3: float
    hole_diameter_mm: float
    charge_length_m: float
    charge_mass_kg: float
    volume_per_hole_m3: float
    burden_m: float
    spacing_m: float
    burden_to_diameter: float  # W/d — ЛНС к диаметру скважины (обе величины в метрах)
    rock_factor_a: float
    rock_factor: kr.RockFactorBreakdown | None  # None — расчёт «до исправления»
    re_weight: float
    strength_exponent: str
    x50_mm: float
    uniformity_n_raw: float
    uniformity_n: float
    charge_to_bench: float | None  # L/H; в расчёте «до исправления» не участвует
    characteristic_size_mm: float
    oversize_pct: float


@dataclass(frozen=True)
class QSelection:
    """Подобранный q: расчёт в этой точке и достигнут ли порог негабарита."""

    point: BlastPoint
    reached: bool

# --- БЛОК ВЫЧИСЛЕНИЙ (Движок расчета) ---

class BlastEngine:
    # Метод-приемщик: срабатывает один раз при создании "движка", инициализирует данные об объектах
    def __init__(self, rock: RockProperties, explosive: ExplosiveProperties, target: TargetParams):
        self.rock = rock            # Запоминаем данные о породе внутри объекта
        self.explosive = explosive  # Запоминаем данные о взрывчатке
        self.target = target        # Запоминаем целевые настройки

    # Rock factor A and RE_weight live in simulation.fragmentation (BDX-006).
    def _get_rock_factor(self):
        return rock_factor_A(self.rock.ucs_mpa, self.rock.density_t_m3)

    def _get_re_weight(self) -> float:
        return relative_weight_strength(self.explosive.power_mj_kg)

    def _charge(self, diameter_mm: float) -> tuple[float, float, float]:
        """Диаметр скважины (м), длина заряда (м) и масса заряда (кг) для коронки."""
        d_m = diameter_mm / 1000 * self.target.hole_oversize_coeff  # фактический диаметр скважины
        total_depth_m = self.target.bench_height_m + self.target.overdrill_m  # общая глубина скважины
        cap_m = (math.pi * (d_m ** 2) / 4) * (self.explosive.density_t_m3 * 1000)  # вместимость 1 п.м.
        charge_mass = cap_m * total_depth_m * FILL_RATIO
        return d_m, total_depth_m * FILL_RATIO, charge_mass

    def _burden(self, charge_mass: float, q: float) -> tuple[float, float]:
        """Объём породы на скважину V = Q/q и ЛНС W = √(V / (a/W · H))."""
        v_hole = charge_mass / q
        W = math.sqrt(v_hole / (self.target.spacing_coeff_m * self.target.bench_height_m))
        return v_hole, W

    def _hole(self, diameter_mm: float, q: float) -> tuple[float, float, float, float, float, float]:
        """Общий пролог legacy_point и kuzram_point: геометрия скважины и заряда при q.

        Отдаёт d_m, charge_length, charge_mass, v_hole, W, m — только вызовы
        _charge/_burden и чтение spacing_coeff_m, без собственной арифметики.
        """
        d_m, charge_length, charge_mass = self._charge(diameter_mm)
        v_hole, W = self._burden(charge_mass, q)
        m = self.target.spacing_coeff_m
        return d_m, charge_length, charge_mass, v_hole, W, m

    # --- Расчёт «до исправления»: только для сравнения на переходный период ---

    def legacy_point(self, diameter_mm: float, q: float) -> BlastPoint:
        """Прежняя модель: A не по Каннингему, показатель 19/30, n с диаметром в метрах (n ≥ 0,8)."""
        d_m, charge_length, charge_mass, v_hole, W, m = self._hole(diameter_mm, q)
        A = self._get_rock_factor()
        re_weight = self._get_re_weight()
        x50_mm = kuznetsov_x50_mm(A, q, charge_mass, re_weight)
        n_raw = _legacy_uniformity_raw(W, d_m, m)
        n = cunningham_uniformity_n(W, d_m, m)
        return BlastPoint(
            q_kg_m3=q, hole_diameter_mm=d_m * 1000, charge_length_m=charge_length,
            charge_mass_kg=charge_mass, volume_per_hole_m3=v_hole, burden_m=W, spacing_m=m * W,
            burden_to_diameter=W / d_m,
            rock_factor_a=A, rock_factor=None, re_weight=re_weight, strength_exponent="19/30",
            x50_mm=x50_mm, uniformity_n_raw=n_raw, uniformity_n=n, charge_to_bench=None,
            characteristic_size_mm=rosin_rammler_characteristic_mm(x50_mm, n),
            oversize_pct=rosin_rammler_oversize_pct(x50_mm, n, self.target.lump_size_mm),
        )

    def optimize_blast_legacy(self, diameter_mm: float, max_oversize_threshold: float = 5.0) -> QSelection:
        """Прежний подбор: q от 0,30 до 1,50, негабарит округляется до сотых перед сравнением."""
        q = 0.3
        step = 0.01
        while q <= 1.5:
            point = self.legacy_point(diameter_mm, q)
            if round(point.oversize_pct, 2) <= max_oversize_threshold:
                return QSelection(point, True)
            q += step
        return QSelection(self.legacy_point(diameter_mm, 1.5), False)  # Если предел достигнут

    # --- Kuz-Ram по Каннингему ---

    def kuzram_point(self, diameter_mm: float, q: float, settings: kr.KuzRamSettings) -> BlastPoint:
        """Расчёт коронки при заданном q по Kuz-Ram (Каннингем, EFEE 2005)."""
        d_m, charge_length, charge_mass, v_hole, W, m = self._hole(diameter_mm, q)
        rock = kr.rock_factor(
            settings,
            ucs_mpa=self.rock.ucs_mpa,
            density_t_m3=self.rock.density_t_m3,
            fissuring_per_m=self.rock.fissuring_ff,
            burden_m=W,
            spacing_m=m * W,
        )
        re_weight = self._get_re_weight()
        x50_mm = kr.mean_fragment_mm(rock.value, q, charge_mass, re_weight, settings.exponent)
        n = kr.uniformity_index(
            burden_m=W,
            hole_diameter_mm=d_m * 1000,
            spacing_to_burden=m,
            drill_deviation_m=settings.drill_deviation_m,
            charge_length_m=charge_length,
            bench_height_m=self.target.bench_height_m,
            correction=settings.uniformity_correction,
        )
        xc, oversize_pct = kr.oversize(x50_mm, n.value, self.target.lump_size_mm)
        return BlastPoint(
            q_kg_m3=q, hole_diameter_mm=d_m * 1000, charge_length_m=charge_length,
            charge_mass_kg=charge_mass, volume_per_hole_m3=v_hole, burden_m=W, spacing_m=m * W,
            burden_to_diameter=W / d_m,
            rock_factor_a=rock.value, rock_factor=rock, re_weight=re_weight,
            strength_exponent=settings.strength_exponent, x50_mm=x50_mm,
            uniformity_n_raw=n.raw, uniformity_n=n.value, charge_to_bench=n.charge_to_bench,
            characteristic_size_mm=xc, oversize_pct=oversize_pct,
        )

    def optimize_blast(
        self,
        diameter_mm: float,
        max_oversize_threshold: float = 5.0,
        settings: kr.KuzRamSettings | None = None,
    ) -> QSelection:
        """Наименьший q (шаг 0,01 от 0,10 до верхней границы), при котором негабарит не больше порога."""
        settings = settings or kr.KuzRamSettings()
        first = round(kr.Q_MIN_KG_M3 * 100)
        # floor, не round: у верхней границы 1.557 не должен стать 1.56 —
        # тогда «порог не достигнут» может отдать q выше запрошенного предела.
        last = math.floor(settings.q_max_kg_m3 * 100 + 1e-9)
        for i in range(first, last + 1):
            point = self.kuzram_point(diameter_mm, i / 100, settings)
            if point.oversize_pct <= max_oversize_threshold:
                return QSelection(point, True)
        return QSelection(self.kuzram_point(diameter_mm, last / 100, settings), False)

    def calibrate_rock_factor(
        self,
        diameter_mm: float,
        q: float,
        oversize_pct: float,
        settings: kr.KuzRamSettings,
    ) -> float | None:
        """C(A), при котором Kuz-Ram при фактическом q даёт фактический негабарит; None — вне 0,1–10."""

        def oversize_at(correction: float) -> float:
            trial = replace(settings, rock_factor_correction=correction)
            return self.kuzram_point(diameter_mm, q, trial).oversize_pct

        return kr.solve_rock_factor_correction(oversize_at, oversize_pct)

# --- ИСПОЛНЯЕМЫЙ БЛОК (Запуск оптимизации) ---

if __name__ == "__main__":
    # 1. Инициализация данных
    rock = RockProperties("Габбро-диабаз", 2.9, 168, 2.2) # Характеристики породы
    # ВВ задаётся теплотой взрыва Q_exp (МДж/кг). RE_weight = 2.99/4.184 ≈ 0.71 (эмульсия слабее ТНТ по энергии на кг)
    explosive = ExplosiveProperties("ЭВЕРСИН Э-100", 1.12, 2.99)
    # Цель: кусок не более 400мм, высота уступа 10м
    target = TargetParams(lump_size_mm=400, hole_diameter_mm=0, bench_height_m=10.0)

    engine = BlastEngine(rock, explosive, target)
    
    # 2. Список доступных диаметров коронок (мм)
    crowns = CROWNS_MM
    
    # Желаемый порог негабарита (например, не более 5%)
    MAX_OVERSIZE = 5

    print(f"--- Оптимизация параметров BlastEX для порога негабарита < {MAX_OVERSIZE}% ---")
    print(f"{'Коронка (мм)':<10} | {'Уд.расход':<10} | {'ЛНС W (м)':<10} | {'Сетка a×b (м)':<18} | {'x50 (мм)':<10}")
    print("-" * 72)

    for d in crowns:
        result = engine.optimize_blast(d, max_oversize_threshold=MAX_OVERSIZE)
        point = result.point
        w_val = round(point.burden_m, 2)
        # Сетка: a — расстояние между скважинами в ряду, b = W (ЛНС)
        a_m = round(engine.target.spacing_coeff_m * w_val, 2)
        grid_str = f"{a_m} × {w_val}"
        mark = "" if result.reached else " (порог не достигнут)"
        print(f"{d:<10} | {round(point.q_kg_m3, 2):<10} | {w_val:<10} | {grid_str:<18} | {round(point.x50_mm, 1):<10}{mark}")

    print("-" * 72)
    print("Расчет завершен. Параметры ЛНС и сетки скважин подобраны автоматически.")