"""Выгрузка значений эталона ВМ.09.03 (блок 66) в JSON-фикстуру тестов TASK-018.

Excel на сервере не исполняется: форму сначала пересчитывает LibreOffice,
скрипт читает значения формул и пишет `tests/fixtures/mass_blast/block66_form_v0.11.json`
(без ФИО и реквизитов). Пересборка на новой версии формы:

    soffice --headless --convert-to xlsx --outdir /tmp/recalc "ВМ.09.03 … форма v0.11.xlsx"
    python scripts/export_mass_blast_fixture.py "ВМ.09.03 … форма v0.11.xlsx" \
        "/tmp/recalc/ВМ.09.03 … форма v0.11.xlsx" tests/fixtures/mass_blast/block66_form_v0.11.json
"""
import hashlib, json, subprocess, sys, datetime as dt
import openpyxl

src, recalc, out = sys.argv[1:4]
wb = openpyxl.load_workbook(recalc, data_only=True)
req = wb["Реквизиты"]
labels = {}
for row in req.iter_rows(min_row=1, max_row=req.max_row):
    b, c = row[1].value, row[2].value
    if b and c is not None:
        labels[str(b).strip()] = c

def R(label):
    return labels[label]

inputs = {
    "block": R("Блок №"), "horizon_m": R("Горизонт, м"),
    "hardness_f": R("Крепость пород f (по Протодьяконову)"),
    "area_m2": R("Площадь блока, м²"),
    "volume_contour_m3": R("Объём взрываемого массива, м³ (по маркшейдерскому контуру)"),
    "bit_mm": R("Диаметр долота, мм"), "reaming_k": R("Коэффициент разбуривания"),
    "explosive": R("ВВ основного заряда (наименование)"),
    "density_kg_m3": R("Плотность заряжания ВВ, кг/м³"),
    "primer": R("Промежуточный детонатор (наименование)"), "primer_mass_kg": R("Масса единицы ПД, кг"),
    "nsi_downhole": R("НСИ скважинные (марка, замедление)"),
    "nsi_surface_holes": R("НСИ поверхностные между скважинами (марка)"),
    "delay_between_holes_ms": R("Интервал замедления между скважинами, мс"),
    "nsi_surface_rows": R("НСИ поверхностные между рядами (марка)"),
    "delay_between_rows_ms": R("Интервал замедления между рядами, мс"),
    "starter": R("Стартовое устройство (марка)"),
    "primer_from_bottom_m": R("Боевик от дна скважины, м"),
    "q_tp_kg_m3": R("Удельный расход ВВ проектный (по ТП), кг/м³"),
    "k_g": R("K_г — грунт в основании охраняемых объектов"),
    "k_s": R("K_с — тип здания (сооружения)"),
    "alpha": R("α — условия взрывания"),
    "people_min_m": R("Минимальное расстояние для людей по прил. 21, м"),
    "k_r": R("K_р — поправка на рельеф (п. 785)"),
    "rock_group_v_or_lower": R("Породы V группы и ниже — уменьшение УВВ ×0,5 (п. 804)") == "да",
    "buildings_damaged": R("Были повреждения зданий от взрывов (×2, п. 795)") == "да",
    "rock_group_ix_or_higher": R("Породы IX группы и выше (×1,5, п. 804)") == "да",
    "frost": R("Отрицательная температура воздуха (×1,5, п. 807)") == "да",
    "k_mech": R("Доля зоны разлёта для механизмов (принято проектом)"),
    "surface_between_holes_pcs": R("Поверхностные НСИ между скважинами по схеме, шт"),
    "surface_between_rows_pcs": R("Поверхностные НСИ между рядами по схеме, шт"),
    "starters_pcs": R("Стартовых устройств по проекту, шт"),
}
# охраняемые объекты (п. 5а): строки после заголовка «Объект»
objects = []
hdr = next(r for r in range(1, req.max_row + 1) if req.cell(r, 2).value == "Объект")
for r in range(hdr + 1, hdr + 6):
    name = req.cell(r, 2).value
    if name:
        objects.append({"name": name, "distance_m": req.cell(r, 3).value, "factor": req.cell(r, 4).value})

pt = wb["Таблица параметров"]
cols = {"n": 1, "d_mm": 2, "bench_height_m": 3, "depth_m": 4, "subdrill_m": 6, "lspp_m": 9, "a_m": 11, "b_m": 13,
        "charge_kg_form": 15, "stemming_m": 17, "primers_pcs": 19, "note": 20, "volume_m3": 21, "eta_z": 22,
        "flyrock_r_m": 23, "nsi_downhole_pcs": 24, "nsi_surface_pcs": 25, "primer_kg": 26, "q_kg_m3": 27}
holes, r = [], 8
while isinstance(pt.cell(r, 1).value, (int, float)):
    holes.append({k: pt.cell(r, c).value for k, c in cols.items()})
    r += 1
tot_row = r
totals = {k: pt.cell(tot_row, c).value for k, c in cols.items() if k not in ("n", "d_mm", "bench_height_m", "note")}
p_lin = pt["AD5"].value

tr = wb["Технический расчёт"]
cell = {}
for row in tr.iter_rows():
    for c in row:
        if c.column == 3 and c.value:
            cell[str(c.value).strip()] = (tr.cell(c.row, 6).value, tr.cell(c.row, 8).value, c.row)
def T(label):
    return cell[label][0]
cons = []
start = next(rw for rw in range(1, tr.max_row + 1) if tr.cell(rw, 3).value == "Наименование")
for rw in range(start + 1, start + 7):
    cons.append({"item": tr.cell(rw, 2).value, "name": tr.cell(rw, 3).value, "qty": tr.cell(rw, 6).value,
                 "unit": tr.cell(rw, 7).value, "mass_kg": tr.cell(rw, 8).value})
qe_row = cell["Qэ — эквивалентная масса"][2]
seis_row = cell["rс (расчёт)"][2]
tech = {
    "p_kg_m": T("Вместимость 1 м, P"),
    "typical_charge_kg": T("Заряд типовой скважины, Q"),
    "explosive_mass_and_max_text": T("Масса ВВ в блоке (сумма по скважинам) / макс. заряд"),
    "q_calc_kg_m3": T("Удельный расход ВМ расчётный, q"),
    "yield_m3_per_m": T("Выход горной массы с 1 п. м"),
    "flyrock_max_m": T("rразл максимальное по скважинам"),
    "people_zone_m": T("Опасная зона для людей (принято)"),
    "mech_zone_m": T("Для механизмов (принято проектом)"),
    "kz_and_n_text": T("Kз (по мин. lзаб/d) / N — скважин в группе"),
    "uvv_n": tr.cell(qe_row, 10).value, "uvv_kz": tr.cell(qe_row, 11).value,
    "q_e_kg": T("Qэ — эквивалентная масса"),
    "uvv_k_product": T("Коэффициенты: замедление (п. 806) × порода (п. 804) × мороз (п. 807)"),
    "r_v_m": T("rв — по остеклению (расчёт)"),
    "r_v_accepted_m": T("Безопасное расстояние по остеклению (принято)"),
    "seis_text": T("Q / N / Kг / Kс / α"),
    "seis_q_kg": tr.cell(seis_row, 10).value, "seis_n": tr.cell(seis_row, 11).value,
    "r_c_m": T("rс (расчёт)"),
    "r_c_accepted_m": T("Сейсмически безопасное расстояние (принято)"),
    "min_stem_to_d": tr["G45"].value,
    "consumption": cons,
}
obj_rows = []
hdr2 = next(rw for rw in range(1, tr.max_row + 1) if tr.cell(rw, 3).value == "Охраняемый объект")
for rw in range(hdr2 + 1, hdr2 + 6):
    if tr.cell(rw, 3).value:
        obj_rows.append({"name": tr.cell(rw, 3).value, "factor": tr.cell(rw, 4).value, "distance_m": tr.cell(rw, 6).value,
                         "safe_m": tr.cell(rw, 7).value, "position": tr.cell(rw, 9).value})
ver = subprocess.run(["soffice", "--version"], capture_output=True, text=True).stdout.strip()
data = {
    "about": "Значения эталона ВМ.09.03 v0.11, блок 66, после пересчёта формул в LibreOffice. ФИО и реквизиты не выгружаются. "
             "Масса заряда charge_kg_form — «формула формы» MROUND((L − l_заб)·P, 5), не расчёт BlastEX по декам.",
    "source": {"file": "ВМ.09.03 Проект массового взрыва — форма v0.11.xlsx",
               "sha256": hashlib.sha256(open(src, "rb").read()).hexdigest(),
               "recalculated_with": ver, "exported_on": dt.date.today().isoformat()},
    "inputs": inputs, "protected_objects": objects, "p_kg_m": p_lin,
    "holes": holes, "totals": totals, "technical_calculation": tech, "protected_objects_result": obj_rows,
}
with open(out, "w", encoding="utf-8") as fh:
    json.dump(data, fh, ensure_ascii=False, indent=1, default=str)
    fh.write("\n")
print(len(holes), totals, json.dumps(tech, ensure_ascii=False)[:900])
