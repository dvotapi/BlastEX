/**
 * Кольцо слагаемых стоимости погонного метра: статьи станка (оснастка, ДТ,
 * запчасти, амортизация, страховка, ТОиР; затраты станка по правилам), услуги сторонних организаций
 * (выпуск на линию и медосмотр, трал, правила затрат бурения), ФОТ экипажа и
 * ФОТ ИТР и ремонтного персонала, закреплённого за бурением.
 * Геометрия — `ringSegmentPath` из кольца структуры себестоимости; в центре —
 * цена метра с ФОТ. Легенда — доли и ₽/м; пробные значения меняют и кольцо.
 * Подстатьи групп (должности, услуги, персонал участка) идут тонким внешним кольцом напротив своего сегмента и
 * подстроками легенды; статьи ФОТ должности (оклад, межвахта, отчисления…) — третьим уровнем легенды, без кольца.
 * У каждой строки легенды — доля, ₽/м и сумма на блок; под должностью — сколько людей в смене и в штате и
 * смен блока, под окладом — оклад одного человека (`note`).
 */
import { useState } from "react";
import type { DrillingComponent } from "../../../types/blockEconomics";
import { ringSegmentPath } from "../donut";
import { money, percent } from "../format";

const RADIUS = 48;
const THICKNESS = 16;
/** Внешнее кольцо подстатей: зазор и толщина. */
const OUTER_GAP = 2;
const OUTER_THICKNESS = 5;
const OUTER = RADIUS + OUTER_GAP + OUTER_THICKNESS;
/** Оттенки подстатей по группе — от тёмного к светлому тону своего сегмента. */
const PART_PALETTES: Record<string, string[]> = {
  CREW_PAYROLL: ["#145c44", "#2f8f6a", "#5fb08d", "#93cdb3", "#c3e3d4"],
  SERVICES: ["#8e3f6b", "#b05b8a", "#cc84ab", "#e2b0cb", "#f0d6e4"],
  RIG_RULES: ["#a88a2a", "#c9a940", "#e0c25a", "#ecd894", "#f5ebc8"],
  CAMP: ["#4f45a0", "#7a6fd0", "#a59de0", "#cdc8ef"],
  SITE_STAFF: ["#245f72", "#3f8fa8", "#6fb2c6", "#a3d0de", "#d1e8ef"],
  PAYROLL_CHARGES: ["#4a6b2a", "#6f9440", "#9cbc6e", "#c6dba6"],
  UNIT_FIXED: ["#7d6c3a", "#a48f55", "#c4b27f", "#ddd0aa", "#eee7d3"],
};
const DEFAULT_PALETTE = ["#6b7680", "#8a949d", "#aab2b9", "#c9cfd4"];

/** Цвета по коду слагаемого; неизвестный код — серый. */
export const COMPONENT_COLORS: Record<string, string> = {
  DRILL_TOOLING: "#3b82f6",
  DRILL_FUEL: "#8b7cf6",
  DRILL_SPARE_PARTS: "#5cc4d8",
  DRILL_DEPRECIATION: "#f28c5f",
  DRILL_INSURANCE: "#c9b2f0",
  DRILL_MAINTENANCE: "#f2a93b",
  DRILL_INSPECTION: "#9aa5b1",
  RIG_RULES: "#e0c25a",
  SERVICES: "#c46a9a",
  CAMP: "#7a6fd0",
  CREW_PAYROLL: "#1f7a5c",
  SITE_STAFF: "#3f8fa8",
  PAYROLL_CHARGES: "#7fa34c",
  UNIT_FIXED: "#b8a36a",
};

export type DonutPart = DrillingComponent & { share: number; path: string; color: string };

/** Сумма на блок: из ответа, а у старого ответа без неё — ₽/м × метры не восстановить, пусто. */
const blockSum = (item: DrillingComponent) => (item.rub === undefined ? "" : money(item.rub, 0));
export type DonutSlice = DrillingComponent & { share: number; path: string; color: string; partSlices: DonutPart[] };

/** Сегменты по порядку слагаемых, нулевые и отрицательные пропущены. */
export function donutSlices(components: DrillingComponent[]): DonutSlice[] {
  const total = components.reduce((sum, item) => sum + Math.max(0, item.rub_per_m), 0);
  if (!(total > 0)) return [];
  let angle = 0;
  const slices: DonutSlice[] = [];
  for (const item of components) {
    if (!(item.rub_per_m > 0)) continue;
    const share = item.rub_per_m / total;
    const partSlices: DonutPart[] = [];
    let partAngle = angle;
    (item.parts ?? []).forEach((part, index) => {
      if (!(part.rub_per_m > 0)) return;
      const partShare = part.rub_per_m / total;
      const palette = PART_PALETTES[item.code] ?? DEFAULT_PALETTE;
      partSlices.push({
        ...part,
        // Доля подстроки — от всей цены метра, как у слагаемых: строки легенды сравнимы.
        share: partShare,
        path: ringSegmentPath(OUTER, OUTER - OUTER_THICKNESS, partAngle, partAngle + partShare * 360),
        color: palette[index % palette.length],
      });
      partAngle += partShare * 360;
    });
    slices.push({
      ...item,
      share,
      path: ringSegmentPath(RADIUS, RADIUS - THICKNESS, angle, angle + share * 360),
      color: COMPONENT_COLORS[item.code] ?? "#9aa5b1",
      partSlices,
    });
    angle += share * 360;
  }
  return slices;
}

/** Подпись строки легенды и пояснение под ней (штат должности, оклад на человека). */
function Label({ item }: { item: DrillingComponent }) {
  return (
    <span className="donut-legend-label">
      {item.label}
      {item.note && <small className="donut-legend-note">{item.note}</small>}
    </span>
  );
}

export function DrillingPriceDonut({ components, stale }: { components: DrillingComponent[]; stale?: boolean }) {
  const [active, setActive] = useState("");
  const slices = donutSlices(components);
  const total = slices.reduce((sum, item) => sum + item.rub_per_m, 0);
  if (slices.length === 0) return null;
  const parts = slices.flatMap((item) => item.partSlices);
  // Наведена статья ФОТ должности — подсвечиваются её должность и группа.
  const owner = parts.find((part) => (part.parts ?? []).some((sub) => sub.code === active));
  const lit = new Set([active, owner?.code ?? "", owner ? (slices.find((slice) => slice.partSlices.includes(owner))?.code ?? "") : ""]);
  const current =
    slices.find((item) => item.code === active) ??
    parts.find((part) => part.code === active) ??
    parts.flatMap((part) => part.parts ?? []).find((sub) => sub.code === active) ??
    null;

  return (
    <figure className={`price-donut${stale ? " is-stale" : ""}`} aria-label="Слагаемые стоимости метра">
      <svg viewBox={`${-OUTER - 2} ${-OUTER - 2} ${2 * OUTER + 4} ${2 * OUTER + 4}`} role="img">
        <title>Слагаемые стоимости метра</title>
        {slices.map((slice) => (
          <path
            key={slice.code}
            d={slice.path}
            fill={slice.color}
            className={`donut-segment${active && !lit.has(slice.code) ? " is-dimmed" : ""}${active === slice.code ? " is-selected" : ""}`}
            onMouseEnter={() => setActive(slice.code)}
            onMouseLeave={() => setActive("")}
            onFocus={() => setActive(slice.code)}
            onBlur={() => setActive("")}
            onClick={() => setActive((current) => (current === slice.code ? "" : slice.code))}
            tabIndex={0}
            aria-label={`${slice.label}: ${money(slice.rub_per_m)} ₽/м, ${percent(slice.share)}`}
          />
        ))}
        {slices.flatMap((slice) =>
          slice.partSlices.map((part) => (
            <path
              key={part.code}
              d={part.path}
              fill={part.color}
              className={`donut-segment donut-part${active && !lit.has(part.code) && active !== slice.code ? " is-dimmed" : ""}`}
              onMouseEnter={() => setActive(part.code)}
              onMouseLeave={() => setActive("")}
            >
              <title>{`${part.label}: ${money(part.rub_per_m)} ₽/м`}</title>
            </path>
          )),
        )}
        <text className="donut-center-value" textAnchor="middle" y={-2} fontSize={13}>
          {current ? money(current.rub_per_m, 0) : money(total, 0)}
        </text>
        <text className="donut-center-unit" textAnchor="middle" y={11}>
          {current ? current.label : "₽/м с ФОТ"}
        </text>
      </svg>
      <ul className="price-donut-legend">
        <li className="price-donut-head" aria-hidden="true">
          <i />
          <span />
          <span>доля</span>
          <span>₽/м</span>
          <span>₽ на блок</span>
        </li>
        {slices.flatMap((slice) => [
          <li
            key={slice.code}
            className={active === slice.code ? "is-active" : ""}
            onMouseEnter={() => setActive(slice.code)}
            onMouseLeave={() => setActive("")}
            onClick={() => setActive((current) => (current === slice.code ? "" : slice.code))}
          >
            <i className="donut-legend-color" style={{ background: slice.color }} />
            <span className="donut-legend-label">{slice.label}</span>
            <span className="donut-legend-percent">{percent(slice.share)}</span>
            <span className="donut-legend-value">{money(slice.rub_per_m, 0)}</span>
            <span className="donut-legend-block">{blockSum(slice)}</span>
          </li>,
          ...slice.partSlices.flatMap((part) => [
            <li
              key={part.code}
              className={`price-donut-part${active === part.code ? " is-active" : ""}`}
              onMouseEnter={() => setActive(part.code)}
              onMouseLeave={() => setActive("")}
            >
              <i className="donut-legend-color" style={{ background: part.color }} />
              <Label item={part} />
              <span className="donut-legend-percent">{percent(part.share)}</span>
              <span className="donut-legend-value">{money(part.rub_per_m, 0)}</span>
              <span className="donut-legend-block">{blockSum(part)}</span>
            </li>,
            ...(part.parts ?? []).map((sub) => (
              <li
                key={sub.code}
                className={`price-donut-subpart${active === sub.code ? " is-active" : ""}`}
                onMouseEnter={() => setActive(sub.code)}
                onMouseLeave={() => setActive("")}
              >
                <i />
                <Label item={sub} />
                <span className="donut-legend-percent">{total > 0 ? percent(sub.rub_per_m / total) : ""}</span>
                <span className="donut-legend-value">{money(sub.rub_per_m, 0)}</span>
                <span className="donut-legend-block">{blockSum(sub)}</span>
              </li>
            )),
          ]),
        ])}
      </ul>
    </figure>
  );
}
