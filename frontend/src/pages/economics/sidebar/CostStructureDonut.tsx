/**
 * Кольцевая диаграмма структуры себестоимости блока.
 *
 * Инлайновый SVG без библиотек графиков: геометрия сегментов уже посчитана
 * в `donut.ts` (`donutSegments`) по разделам `estimateModel.ts` — здесь
 * только разметка, обработчики и подписи. Доли, суммы и ₽/м³ — готовые
 * числа из `EstimateGroup`, ничего не пересчитывается.
 */
import { useMemo, useState, type KeyboardEvent } from "react";
import { donutSegments } from "../donut";
import type { EstimateGroup, EstimateGroupCode } from "../estimateModel";
import { money, percent } from "../format";

/** Радиус и толщина кольца в локальных координатах SVG (центр — 0,0). */
const RADIUS = 82;
const THICKNESS = 26;

type Unit = "₽" | "₽/м³";

export function CostStructureDonut(props: {
  groups: EstimateGroup[];
  costPerM3: number | null;
  unit: Unit;
  onUnitChange: (unit: Unit) => void;
  highlighted: EstimateGroupCode | null;
  onSelect: (code: EstimateGroupCode) => void;
}) {
  const { groups, costPerM3, unit, onUnitChange, highlighted, onSelect } = props;
  const segments = useMemo(() => donutSegments(groups, RADIUS, THICKNESS), [groups]);
  const [hovered, setHovered] = useState<EstimateGroupCode | null>(null);
  const caption = segments.find((segment) => segment.code === hovered) ?? null;

  const select = (code: EstimateGroupCode) => () => onSelect(code);
  const selectOnKey = (code: EstimateGroupCode) => (event: KeyboardEvent<SVGPathElement>) => {
    if (event.key !== "Enter" && event.key !== " ") return;
    event.preventDefault();
    onSelect(code);
  };

  return (
    <div className="donut-panel">
      <div className="donut-unit-switch" role="group" aria-label="Единица легенды">
        <button
          type="button"
          className={unit === "₽" ? "is-active" : undefined}
          aria-pressed={unit === "₽"}
          onClick={() => onUnitChange("₽")}
        >
          ₽
        </button>
        <button
          type="button"
          className={unit === "₽/м³" ? "is-active" : undefined}
          aria-pressed={unit === "₽/м³"}
          onClick={() => onUnitChange("₽/м³")}
        >
          ₽/м³
        </button>
      </div>

      <svg viewBox="0 0 200 200" role="img" aria-labelledby="donut-title">
        <title id="donut-title">Структура себестоимости блока по разделам</title>
        <g transform="translate(100,100)">
          {segments.map((segment) => (
            <path
              key={segment.code}
              d={segment.path}
              fill={segment.color}
              role="button"
              tabIndex={0}
              aria-label={`${segment.label}: ${money(segment.value, 0)} ₽, доля ${percent(segment.share)}`}
              className={[
                "donut-segment",
                highlighted === segment.code ? "is-selected" : "",
                highlighted !== null && highlighted !== segment.code ? "is-dimmed" : "",
              ]
                .filter(Boolean)
                .join(" ")}
              onClick={select(segment.code)}
              onKeyDown={selectOnKey(segment.code)}
              onMouseEnter={() => setHovered(segment.code)}
              onMouseLeave={() => setHovered(null)}
              onFocus={() => setHovered(segment.code)}
              onBlur={() => setHovered(null)}
            >
              <title>
                {`${segment.label}: ${money(segment.value, 0)} ₽ (${percent(segment.share)})`}
              </title>
            </path>
          ))}
        </g>
        <text x="100" y="94" textAnchor="middle" className="donut-center-value">
          {costPerM3 === null ? "—" : money(costPerM3)}
        </text>
        <text x="100" y="110" textAnchor="middle" className="donut-center-unit">
          ₽/м³
        </text>
        <text x="100" y="127" textAnchor="middle" className="donut-center-caption">
          Себестоимость
        </text>
      </svg>

      <div className="donut-caption" aria-hidden={caption === null}>
        {caption && (
          <>
            <b>{caption.label}</b>
            <span>{money(caption.value, 0)} ₽</span>
            <span>{caption.perM3 === null ? "—" : `${money(caption.perM3)} ₽/м³`}</span>
            <span>{percent(caption.share)}</span>
          </>
        )}
      </div>

      <ol className="donut-legend">
        {segments.map((segment) => (
          <li key={segment.code} className={highlighted === segment.code ? "is-active" : undefined}>
            <span className="donut-legend-color" style={{ background: segment.color }} aria-hidden="true" />
            <span className="donut-legend-label">{segment.label}</span>
            <span className="donut-legend-percent">{percent(segment.share)}</span>
            <span className="donut-legend-value">
              {unit === "₽"
                ? `${money(segment.value, 0)} ₽`
                : segment.perM3 === null
                  ? "—"
                  : `${money(segment.perM3)} ₽/м³`}
            </span>
          </li>
        ))}
      </ol>

      <table className="sr-only">
        <caption>Структура себестоимости по разделам</caption>
        <thead>
          <tr>
            <th scope="col">Раздел</th>
            <th scope="col">Доля</th>
            <th scope="col">Сумма, ₽</th>
            <th scope="col">₽/м³</th>
          </tr>
        </thead>
        <tbody>
          {segments.map((segment) => (
            <tr key={segment.code}>
              <td>{segment.label}</td>
              <td>{percent(segment.share)}</td>
              <td>{money(segment.value, 0)}</td>
              <td>{segment.perM3 === null ? "—" : money(segment.perM3)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
