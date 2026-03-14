import math  # Импортируем модуль математики (нужен для ПИ и возведения в степень)
from dataclasses import dataclass  # Импортируем декоратор для создания удобных структур данных 

# --- БЛОК ОПИСАНИЯ ДАННЫХ (Коробки с информацией) ---

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
    power_mj_kg: float            # Теплота взрыва Q_exp (МДж/кг). RE_weight = 4.184/Q_exp, E = RE_weight*115 для формулы Кузнецова

@dataclass
class TargetParams:
    lump_size_mm: float # Кондиционный размер куска, который мы считаем негабаритом (мм)
    hole_diameter_mm: float # Диаметр скважины (коронки) в миллиметрах
    overdrill_m: float = 1.0          # Фиксированный перебур в метрах
    hole_oversize_coeff: float = 1.05     # Коэффициент разбуривания (увеличение диаметра скважины относительно диаметра коронки)
    spacing_coeff_m: float = 1.25 # Коэффициент сетки (на сколько "а" больше чем "W")
    bench_height_m: float = 10.0 # Высота уступа в карьере в метрах
   
# --- БЛОК ВЫЧИСЛЕНИЙ (Движок расчета) ---

class BlastEngine:
    # Метод-приемщик: срабатывает один раз при создании "движка", инициализирует данные об объектах
    def __init__(self, rock: RockProperties, explosive: ExplosiveProperties, target: TargetParams):
        self.rock = rock            # Запоминаем данные о породе внутри объекта
        self.explosive = explosive  # Запоминаем данные о взрывчатке
        self.target = target        # Запоминаем цеелевые настройки

    # Внутренний расчет индекса взрываемости (по формулам Лилли/Kuz-Ram)
    def _get_rock_factor(self):
        # Суммируем факторы прочности, плотности и структуры с коэффициентами
        index = self.rock.ucs_mpa / 20 + self.rock.density_t_m3 * 2.5 + 7
        return 0.12 * index  # Возвращаем итоговое число (Rock Factor "A")

    def _get_re_weight(self) -> float:
        
        return self.explosive.power_mj_kg / 4.184 # Расчет тротилового эквивалента по энергии на кг (Теплота взрыва тротила Q TNT = 4.184 МДж/кг)


    def _get_E_for_kuznetsov(self) -> float:
        return self._get_re_weight() * 115.0 # Расчет индекса E для формулы Кузнецова: E = RE_weight * 115 (АНФО = 100, ТНТ = 115 в шкале формулы).

    def optimize_blast(self, diameter_mm: float, max_oversize_threshold: float = 5.0) -> dict:
        # Подбир минимального удельного расхода q для достижения нужного % негабарита
        q = 0.3
        step = 0.01
        
        while q <= 1.5:
            res = self._calculate_with_q(diameter_mm, q)
            if res['oversize_pct'] <= max_oversize_threshold:
                return {**res, "target_q": round(q, 2)}
            q += step
            
        return self._calculate_with_q(diameter_mm, 1.5) # Если предел достигнут

    def _calculate_with_q(self, diameter_mm: float, q: float) -> dict:
        # Вспомогательный расчет (копия основной логики, но с переменным q)
        d_crown_m = diameter_mm / 1000 # Переводим диаметр коронки из мм в метры
        d_m = d_crown_m * self.target.hole_oversize_coeff # считаем фактический диаметр скважины
        total_depth_m = self.target.bench_height_m + self.target.overdrill_m # считаем общую глубину скважины
        cap_m = (math.pi * (d_m ** 2) / 4) * (self.explosive.density_t_m3 * 1000) # Вместимость 1 погонного метра скважины
        charge_mass = cap_m * total_depth_m * 0.8  # Масса заряда (коэф. заполнения 80%)
        v_hole = charge_mass / q # Объем скважины
        W = math.sqrt(v_hole / (self.target.spacing_coeff_m * self.target.bench_height_m)) # ЛНС
        A = self._get_rock_factor()  # Индекс породы
        # Кузнецов: x50 ∝ (115/E)^(19/30); E = 115·RE_weight ⇒ множитель (1/RE_weight)^(19/30).
        re_weight = self._get_re_weight()
        x50_cm = A * math.pow(q, -0.8) * math.pow(charge_mass, 1/6) * math.pow(re_weight, -19/30)
        x50_mm = x50_cm * 10  # см → мм
        n = max(0.8, (2.2 - 14 * (W / d_m)) * (1 + (self.target.spacing_coeff_m - 1)/2)) # Показатель однородности дробимости
        xc = x50_mm / math.pow(math.log(2), 1/n) # Характеристический размер куска
        oversize = (math.exp(-math.pow(self.target.lump_size_mm / xc, n))) * 100 # Выход негабарита
        
        return {
           "diameter": diameter_mm, # Диаметр скважины
            "W_m": round(W, 2), # ЛНС
            "oversize_pct": round(oversize, 2), # Выход негабарита
            "x50_mm": round(x50_mm, 1), # Средний размер куска
            "q": round(q, 2) # Удельный расход
        }

    # Основная функция для расчета под конкретный диаметр
    def calculate_for_diameter(self, diameter_mm: float) -> dict:
        d_crown_m = diameter_mm / 1000 # Переводим диаметр коронки из мм в метры
        d_m = d_crown_m * self.target.hole_oversize_coeff # считаем фактический диаметр скважины
        total_depth_m = self.target.bench_height_m + self.target.overdrill_m # считаем общую глубину скважины
        cap_m = (math.pi * (d_m ** 2) / 4) * (self.explosive.density_t_m3 * 1000) # Вместимость
        charge_mass = cap_m * total_depth_m * 0.8  # Масса заряда (коэф. заполнения 80%)
        
        # 2. Определяем параметры сетки
        target_q = 1.4  # Задаем желаемый удельный расход (например, 1.4 кг ВВ на 1 куб породы) !!!
        # Считаем массу ВВ в 1 скважине (вместимость * высота * 80% заполнения)
        # charge_mass = cap_m * self.target.bench_height_m * 0.77
        # Вычисляем, какой объем породы эта масса должна взорвать (V = Масса / Расход) !!!
        v_hole = charge_mass / target_q
        
        # Вычисляем ЛНС (W) через обратную формулу объема: W = корень(V / (коэф_сетки * высота))
        W = math.sqrt(v_hole / (self.target.spacing_coeff_m * self.target.bench_height_m))
        
        # 3. Применяем модель Кузнецова (ищем средний размер куска x50)
        A = self._get_rock_factor()
        # Кузнецов: x50 ∝ (1/RE_weight)^(19/30), RE_weight = Q_exp/4.184 — более сильное ВВ даёт меньше x50
        re_weight = self._get_re_weight()
        x50_cm = A * math.pow(target_q, -0.8) * math.pow(charge_mass, 1/6) * math.pow(re_weight, -19/30)
        x50_mm = x50_cm * 10  # см → мм
        
        # 4. Считаем показатель однородности дробимости (n) по Каннингему
        # Он зависит от того, насколько "густо" натыканы скважины относительно их диаметра
        n = (2.2 - 14 * (W / d_m)) * (1 + (self.target.spacing_coeff_m - 1)/2)
        n = max(0.8, n) # Ограничиваем n снизу, чтобы расчет не превратился в абсурд
        
        # 5. Считаем выход негабарита через распределение Розина-Рамблера
        # xc - это характеристический размер куска (математическая константа распределения)
        xc = x50_mm / math.pow(math.log(2), 1/n)
        # Формула дает вероятность встретить кусок больше заданного в lump_size_mm
        oversize = (math.exp(-math.pow(self.target.lump_size_mm / xc, n))) * 100
        
        # Возвращаем результаты в виде словаря (ключ: значение)
        return {
            "diameter": diameter_mm,
            "W_m": round(W, 2),
            "oversize_pct": round(oversize, 2),
            "x50_mm": round(x50_mm, 1)
        }

# --- ИСПОЛНЯЕМЫЙ БЛОК (Запуск оптимизации) ---

if __name__ == "__main__":
    # 1. Инициализация данных
    rock = RockProperties("Габбро-диабаз", 2.9, 168, 2.2) # Характеристики породы
    # ВВ задаётся теплотой взрыва Q_exp (МДж/кг). RE_weight = 4.184/2.99 ≈ 1.40 (эмульсия слабее ТНТ по энергии на кг)
    explosive = ExplosiveProperties("Эмульсия", 1.12, 2.99)
    # Цель: кусок не более 400мм, высота уступа 10м
    target = TargetParams(lump_size_mm=400, hole_diameter_mm=0, bench_height_m=10.0)

    engine = BlastEngine(rock, explosive, target)
    
    # 2. Список доступных диаметров коронок (мм)
    crowns = [130, 140, 152, 165]
    
    # Желаемый порог негабарита (например, не более 5%)
    MAX_OVERSIZE = 5

    print(f"--- Оптимизация параметров BlastEX для порога негабарита < {MAX_OVERSIZE}% ---")
    print(f"{'Коронка (мм)':<10} | {'Уд.расход':<10} | {'ЛНС W (м)':<10} | {'Сетка a×b (м)':<18} | {'x50 (мм)':<10}")
    print("-" * 72)

    for d in crowns:
        res = engine.optimize_blast(d, max_oversize_threshold=MAX_OVERSIZE)
        q_val = res['q']
        w_val = res['W_m']
        x50 = res['x50_mm']
        # Сетка: a — расстояние между скважинами в ряду, b = W (ЛНС)
        a_m = round(engine.target.spacing_coeff_m * w_val, 2)
        b_m = w_val
        grid_str = f"{a_m} × {b_m}"
        print(f"{d:<10} | {q_val:<10} | {w_val:<10} | {grid_str:<18} | {x50:<10}")

    print("-" * 72)
    print("Расчет завершен. Параметры ЛНС и сетки скважин подобраны автоматически.")