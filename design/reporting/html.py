"""Printable official blast passport HTML (BDX-024)."""
from __future__ import annotations

import html
from typing import Any

from design.models import BlastDesign
from design.reporting.engine import build_passport
from design.reporting.types import (
    ROLE_LABELS_EN,
    ROLE_LABELS_RU,
    BlastPassport,
    MetricRow,
)

from design.models import ROLE_DESIGNED, ROLE_EXECUTED, ROLE_MEASURED, ROLE_PREDICTED


def _esc(value: Any) -> str:
    return html.escape(str(value))


def _fmt(value: float | None, places: int = 2, empty: str = "—") -> str:
    if value is None:
        return empty
    text = f"{float(value):.{places}f}"
    if places > 0:
        text = text.rstrip("0").rstrip(".")
    return text


def _cell(value: float | None, places: int = 2) -> str:
    return _fmt(value, places)


def _role_chip(role: str) -> str:
    label = ROLE_LABELS_RU.get(role, role)
    en = ROLE_LABELS_EN.get(role, role)
    return f'<span class="role role-{_esc(role)}">{_esc(label)} / {_esc(en)}</span>'


def _comparison_rows(rows: list[MetricRow]) -> str:
    chunks: list[str] = []
    for row in rows:
        places = 4 if row.unit in {"кг/м³", "мм/с"} else (0 if row.unit in {"шт.", "₽"} else 2)
        chunks.append(
            "<tr>"
            f"<td class=\"left\">{_esc(row.label)}</td>"
            f"<td>{_esc(row.unit)}</td>"
            f"<td class=\"col-designed\">{_cell(row.designed, places)}</td>"
            f"<td class=\"col-executed\">{_cell(row.executed, places)}</td>"
            f"<td class=\"col-predicted\">{_cell(row.predicted, places)}</td>"
            f"<td class=\"col-measured\">{_cell(row.measured, places)}</td>"
            "</tr>"
        )
    return "".join(chunks)


def _hole_rows(document: BlastPassport) -> str:
    chunks: list[str] = []
    for hole in document.holes:
        chunks.append(
            "<tr>"
            f"<td class=\"left\">{_esc(hole.hole_id)}</td>"
            f"<td class=\"left\">{_esc(hole.kind)}</td>"
            f"<td>{hole.collar_x_m:.2f}</td>"
            f"<td>{hole.collar_y_m:.2f}</td>"
            f"<td>{hole.collar_z_m:.2f}</td>"
            f"<td class=\"col-designed\">{hole.designed_length_m:.1f}</td>"
            f"<td class=\"col-designed\">{hole.designed_angle_deg:.0f}</td>"
            f"<td class=\"col-designed\">{hole.designed_azimuth_deg:.0f}</td>"
            f"<td class=\"col-designed\">{hole.designed_diameter_mm:.0f}</td>"
            f"<td class=\"col-designed\">{_fmt(hole.designed_charge_kg, 1, '')}</td>"
            f"<td class=\"col-designed\">{_fmt(hole.designed_q_kg_m3, 3, '')}</td>"
            f"<td class=\"col-executed\">{_fmt(hole.executed_length_m, 1)}</td>"
            f"<td class=\"col-executed\">{_fmt(hole.executed_diameter_mm, 0)}</td>"
            f"<td class=\"col-executed\">{_fmt(hole.executed_charge_kg, 1)}</td>"
            f"<td class=\"left\">{'да' if hole.enabled else 'нет'}</td>"
            "</tr>"
        )
    return "".join(chunks)


def render_passport_html(document: BlastPassport) -> str:
    """Self-contained printable HTML. Predicted values stay visually distinct."""
    designed = document.designed
    predicted = document.predicted
    measured = document.measured
    executed = document.executed
    planned = document.planned_cost
    warnings = "".join(f"<li>{_esc(item)}</li>" for item in document.warnings[:12])
    return f"""<!doctype html>
<html lang="ru"><head><meta charset="utf-8">
<title>Паспорт БВР — {_esc(document.name)}</title>
<style>
  body {{ font-family: "Segoe UI", Arial, sans-serif; margin: 24px; color: #17231d; }}
  h1 {{ font-size: 20px; margin-bottom: 4px; }}
  h2 {{ font-size: 14px; margin: 22px 0 8px; }}
  .subtitle {{ color: #6e7c75; font-size: 12px; margin-bottom: 12px; }}
  .banner {{ border: 1px solid #c9a227; background: #fff8e1; padding: 10px 12px; border-radius: 8px; font-size: 12px; margin-bottom: 16px; }}
  .roles {{ display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 16px; }}
  .role {{ display: inline-block; padding: 3px 8px; border-radius: 999px; font-size: 10px; font-weight: 700; letter-spacing: .02em; }}
  .role-designed {{ background: #e8f3ec; color: #173125; }}
  .role-executed {{ background: #eef2ff; color: #2a3a7a; }}
  .role-predicted {{ background: #fff3d6; color: #6a4a28; }}
  .role-measured {{ background: #fdecea; color: #7a2a22; }}
  .grid {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; margin-bottom: 20px; }}
  .grid div {{ border: 1px solid #dce4e0; border-radius: 8px; padding: 10px; }}
  .grid span {{ display: block; color: #78857f; font-size: 10px; margin-bottom: 4px; }}
  .grid strong {{ font-size: 16px; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 11px; margin-bottom: 24px; }}
  th, td {{ border: 1px solid #e2e8e5; padding: 5px 7px; text-align: right; }}
  th {{ background: #f3f6f4; }}
  td.left, th.left {{ text-align: left; }}
  th.col-designed, td.col-designed {{ background: #f4faf6; }}
  th.col-executed, td.col-executed {{ background: #f5f7ff; }}
  th.col-predicted, td.col-predicted {{ background: #fff8e8; }}
  th.col-measured, td.col-measured {{ background: #fff5f3; }}
  .print-button {{ margin-bottom: 16px; padding: 8px 14px; border: 1px solid #2d7556; border-radius: 8px; background: #2d7556; color: #fff; font-weight: 700; cursor: pointer; }}
  @media print {{ .print-button {{ display: none; }} }}
</style>
</head>
<body>
  <button class="print-button" onclick="window.print()">Печать</button>
  <h1>Паспорт БВР — {_esc(document.name)}</h1>
  <div class="subtitle">
    Обновлён: {_esc(document.updated_at or "—")} · Собран: {_esc(document.generated_at or "—")} ·
    Порода: {_esc(designed.rock_name or "—")} · ВВ: {_esc(designed.explosive_key or "—")} ·
    Система инициирования: {_esc(designed.initiation_system or "—")}
  </div>
  <div class="banner">
    Документ не утверждён автоматически. Прогнозные величины помечены
    {_role_chip(ROLE_PREDICTED)} и не являются замером или решением инженера.
  </div>
  <div class="roles">
    {_role_chip(ROLE_DESIGNED)}
    {_role_chip(ROLE_EXECUTED)}
    {_role_chip(ROLE_PREDICTED)}
    {_role_chip(ROLE_MEASURED)}
  </div>

  <h2>Проектные параметры <small>({_esc(ROLE_LABELS_EN[ROLE_DESIGNED])})</small></h2>
  <div class="grid">
    <div><span>Площадь / объём блока</span><strong>{_fmt(designed.block_volume_m3, 0)} м³</strong></div>
    <div><span>Рабочих скважин</span><strong>{designed.production_hole_count}</strong></div>
    <div><span>Контурных скважин</span><strong>{designed.contour_hole_count}</strong></div>
    <div><span>Погонаж бурения</span><strong>{_fmt(designed.drilling_metres, 0)} м</strong></div>
    <div><span>Масса ВВ на блок</span><strong>{_fmt(designed.explosive_mass_kg, 0)} кг</strong></div>
    <div><span>Средний уд. расход</span><strong>{_fmt(designed.powder_factor_kg_m3, 3)} кг/м³</strong></div>
    <div><span>Сетка a × b</span><strong>{_fmt(designed.spacing_a_m, 1)} × {_fmt(designed.burden_b_m, 1)} м</strong></div>
    <div><span>Диаметр / перебур</span><strong>{_fmt(designed.diameter_mm, 0)} мм / {_fmt(designed.subdrill_m, 1)} м</strong></div>
  </div>

  <h2>Прогнозные исходы <small>({_esc(ROLE_LABELS_EN[ROLE_PREDICTED])})</small></h2>
  <div class="grid">
    <div><span>X50 / X80</span><strong>{_fmt(predicted.x50_mm, 0)} / {_fmt(predicted.x80_mm, 0)} мм</strong></div>
    <div><span>Негабарит</span><strong>{_fmt(predicted.oversize_pct, 2)} %</strong></div>
    <div><span>Модель дробления</span><strong>{_esc(predicted.fragmentation_model or "—")}</strong></div>
    <div><span>MIC / PPV</span><strong>{_fmt(predicted.mic_kg, 1)} кг / {_fmt(predicted.ppv_mm_s, 2)} мм/с</strong></div>
    <div><span>Отброс / вывал</span><strong>{_fmt(predicted.throw_m, 2)} / {_fmt(predicted.heave_m, 2)} м</strong></div>
    <div><span>Развал (оценка)</span><strong>{_esc(predicted.movement_label or "оценка")}</strong></div>
    <div><span>Объём развала</span><strong>{_fmt(predicted.muckpile_volume_m3, 0)} м³</strong></div>
    <div><span>Конвенция SD</span><strong>{_esc(predicted.vibration_convention or "—")}</strong></div>
  </div>

  <h2>Смета</h2>
  <div class="grid">
    <div><span>Плановая смета ({_esc(ROLE_LABELS_EN[ROLE_DESIGNED])})</span><strong>{_fmt(planned.total_amount_rub if planned else None, 0)} ₽</strong></div>
    <div><span>Плановая цена за м³</span><strong>{_fmt(planned.cost_per_m3 if planned else None, 1)} ₽/м³</strong></div>
    <div><span>Фактическая смета ({_esc(ROLE_LABELS_EN[ROLE_MEASURED])})</span><strong>{_fmt(measured.cost_rub, 0)} ₽</strong></div>
    <div><span>Фактическая цена за м³</span><strong>{_fmt(measured.cost_per_m3, 1)} ₽/м³</strong></div>
  </div>

  <h2>Исполнение <small>({_esc(ROLE_LABELS_EN[ROLE_EXECUTED])})</small></h2>
  <div class="grid">
    <div><span>Факт бурения</span><strong>{executed.as_drilled_count} скв.</strong></div>
    <div><span>Факт заряжания</span><strong>{executed.as_charged_count} скв.</strong></div>
    <div><span>Факт взрыва</span><strong>{executed.as_fired_count} скв.</strong></div>
    <div><span>Замерённые исходы</span><strong>{_esc(measured.recorded_at or "нет")}</strong></div>
  </div>

  <h2>Сводная таблица ролей</h2>
  <table class="comparison-table">
    <thead><tr>
      <th class="left">Показатель</th><th>Ед.</th>
      <th class="col-designed">DESIGNED</th>
      <th class="col-executed">EXECUTED</th>
      <th class="col-predicted">PREDICTED</th>
      <th class="col-measured">MEASURED</th>
    </tr></thead>
    <tbody>{_comparison_rows(document.comparison)}</tbody>
  </table>

  <h2>Скважины проекта</h2>
  <table class="holes-table">
    <thead><tr>
      <th class="left">ID</th><th class="left">Тип</th><th>X, м</th><th>Y, м</th><th>Z устья, м</th>
      <th class="col-designed">Длина, м</th><th class="col-designed">Угол, °</th>
      <th class="col-designed">Азимут, °</th><th class="col-designed">⌀, мм</th>
      <th class="col-designed">Заряд, кг</th><th class="col-designed">q, кг/м³</th>
      <th class="col-executed">Факт длина, м</th><th class="col-executed">Факт ⌀, мм</th>
      <th class="col-executed">Факт заряд, кг</th>
      <th class="left">Активна</th>
    </tr></thead>
    <tbody>{_hole_rows(document)}</tbody>
  </table>
  {"<h2>Замечания</h2><ul>" + warnings + "</ul>" if warnings else ""}
</body></html>"""


def passport_html(design: BlastDesign, **kwargs: Any) -> str:
    """Build then render. The design is not rewritten and not approved."""
    document = build_passport(design, **kwargs)
    return render_passport_html(document)
