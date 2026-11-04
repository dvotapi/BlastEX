/**
 * Кольцо слагаемых стоимости погонного метра: статьи строк бурения (оснастка,
 * ДТ, запчасти, амортизация, страховка, ТОиР, медосмотр) и ФОТ экипажа.
 * Геометрия — `ringSegmentPath` из кольца структуры себестоимости; в центре —
 * цена метра с ФОТ. Легенда — доли и ₽/м; пробные значения меняют и кольцо.
 * Подстатьи слагаемого (у ФОТ экипажа — строки должностей) идут тонким внешним кольцом напротив своего сегмента и
 * подстроками легенды.
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
/** Оттенки подстатей ФОТ — от тёмного к светлому зелёному. */
const PART_COLORS = ["#145c44", "#2f8f6a", "#5fb08d", "#93cdb3", "#c3e3d4", "#e0f0e8"];

/** Цвета по коду слагаемого; неизвестный код — серый. */
export const COMPONENT_COLORS: Record<string, string> = {
  DRILL_TOOLING: "#3b82f6",
  DRILL_FUEL: "#8b7cf6",
  DRILL_SPARE_PARTS: "#5cc4d8",
  DRILL_DEPRECIATION: "#f28c5f",
  DRILL_INSURANCE: "#c9b2f0",
  DRILL_MAINTENANCE: "#f2a93b",
  DRILL_INSPECTION: "#9aa5b1",
  CREW_PAYROLL: "#1f7a5c",
};

export type DonutPart = DrillingComponent & { share: number; path: string; color: string };
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
      partSlices.push({
        ...part,
        share: part.rub_per_m / item.rub_per_m,
        path: ringSegmentPath(OUTER, OUTER - OUTER_THICKNESS, partAngle, partAngle + partShare * 360),
        color: PART_COLORS[index % PART_COLORS.length],
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

export function DrillingPriceDonut({ components, stale }: { components: DrillingComponent[]; stale?: boolean }) {
  const [active, setActive] = useState("");
  const slices = donutSlices(components);
  const total = slices.reduce((sum, item) => sum + item.rub_per_m, 0);
  if (slices.length === 0) return null;
  const current =
    slices.find((item) => item.code === active) ?? slices.flatMap((item) => item.partSlices).find((part) => part.code === active) ?? null;

  return (
    <figure className={`price-donut${stale ? " is-stale" : ""}`} aria-label="Слагаемые стоимости метра">
      <svg viewBox={`${-OUTER - 2} ${-OUTER - 2} ${2 * OUTER + 4} ${2 * OUTER + 4}`} role="img">
        <title>Слагаемые стоимости метра</title>
        {slices.map((slice) => (
          <path
            key={slice.code}
            d={slice.path}
            fill={slice.color}
            className={`donut-segment${active && active !== slice.code ? " is-dimmed" : ""}${active === slice.code ? " is-selected" : ""}`}
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
              className={`donut-segment donut-part${active && active !== part.code && active !== slice.code ? " is-dimmed" : ""}`}
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
          </li>,
          ...slice.partSlices.map((part) => (
            <li
              key={part.code}
              className={`price-donut-part${active === part.code ? " is-active" : ""}`}
              onMouseEnter={() => setActive(part.code)}
              onMouseLeave={() => setActive("")}
            >
              <i className="donut-legend-color" style={{ background: part.color }} />
              <span className="donut-legend-label">{part.label}</span>
              <span className="donut-legend-percent">{percent(part.share)} ФОТ</span>
              <span className="donut-legend-value">{money(part.rub_per_m, 0)}</span>
            </li>
          )),
        ])}
      </ul>
    </figure>
  );
}
