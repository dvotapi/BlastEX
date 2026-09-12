import { useMemo } from "react";
import { darken } from "../../components/holeDrawing/palette";
import type { BlastGeometryResponse } from "../../types";
import type { PanelInputs } from "./calcInputs";
import { splitComparison, type DiffRow } from "./comparisonLayout";
import { HoleSchemeView } from "./HoleSchemeView";
import { HoleVariantCard } from "./HoleVariantCard";

export type ComparisonVariant = {
  key: "left" | "right";
  label: string;
  /** Короткая подпись для колонок таблиц сравнения. */
  shortLabel: string;
  color: string;
  initialInputs: PanelInputs;
  onInputsChange: (inputs: PanelInputs) => void;
  geometry: BlastGeometryResponse | null;
  error: string;
};

function Marker({ color }: { color: string }) {
  return <span className="variant-marker" style={{ background: color, borderColor: darken(color, 0.35) }} aria-hidden="true" />;
}

function DiffTable({ title, rows, variants }: { title: string; rows: DiffRow[]; variants: [ComparisonVariant, ComparisonVariant] }) {
  return (
    <table className="diff-table">
      <thead>
        <tr>
          <th scope="col">{title}</th>
          {variants.map((variant) => (
            <th key={variant.key} scope="col" className="num">
              <Marker color={variant.color} />
              {variant.shortLabel}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {rows.map((row) => (
          <tr key={row.label} className={row.flag ? "flagged" : undefined} title={row.flag ? "Обычно одинаково у обоих вариантов, но здесь различается" : undefined}>
            <th scope="row" title={row.label}>{row.label}</th>
            <td className="num">{row.a ?? "—"}</td>
            <td className="num">{row.b ?? "—"}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

/**
 * Нижняя панель листа «Расчёт»: параметры двух вариантов заряда, их разрезы
 * и сравнение по строкам — отличающиеся рядом, общие один раз. Какие строки
 * куда идут, решает `comparisonLayout.ts`; панель только раскладывает.
 */
export function ChargeComparison({
  cardKey,
  variants,
  crownMm,
  gridLabel,
  depthM,
  explosives,
  nsiLengthOptions,
  detonatorDelayOptions,
  blockVolumeM3,
  onBlockVolumeChange,
  additionalHolesPct,
  onAdditionalHolesChange,
}: {
  /** Префикс `key` карточек: смена объекта пересоздаёт их с новыми значениями. */
  cardKey: string;
  variants: [ComparisonVariant, ComparisonVariant];
  crownMm: number;
  gridLabel: string;
  depthM: number;
  explosives: { id?: string; key: string; name: string }[];
  nsiLengthOptions: number[];
  detonatorDelayOptions: number[];
  blockVolumeM3: number;
  onBlockVolumeChange: (value: number) => void;
  additionalHolesPct: number;
  onAdditionalHolesChange: (value: number) => void;
}) {
  const [first, second] = variants;
  const comparison = useMemo(
    () =>
      first.geometry && second.geometry
        ? splitComparison(first.geometry.hole_rows, second.geometry.hole_rows, first.geometry.block_rows, second.geometry.block_rows)
        : null,
    [first.geometry, second.geometry],
  );
  const totalHoles = first.geometry?.block.total_holes ?? second.geometry?.block.total_holes;
  const errors = variants.filter((variant) => variant.error);

  return (
    <section className="panel charge-comparison">
      <header>
        <b>Схема заряда и сравнение вариантов</b>
        <div className="panel-header-actions">
          <span>
            Ø {crownMm} мм · сетка {gridLabel} м{totalHoles !== undefined ? ` · ${totalHoles} скважин` : ""}
          </span>
          <label className="header-field">
            Объём блока, м³
            <input
              type="number"
              className="block-volume-input"
              min={1000}
              step={1000}
              value={blockVolumeM3}
              onChange={(e) => onBlockVolumeChange(Number(e.target.value))}
            />
          </label>
          <label className="header-field">
            Доп. скважины, %
            <input
              type="number"
              className="extra-holes-input"
              min={0}
              max={20}
              step={0.5}
              value={additionalHolesPct}
              onChange={(e) => onAdditionalHolesChange(Number(e.target.value))}
            />
          </label>
        </div>
      </header>
      <div className="charge-comparison-body">
        <div className="vcards">
          {variants.map((variant) => (
            <HoleVariantCard
              key={`${cardKey}-${variant.key}`}
              variantLabel={variant.label}
              color={variant.color}
              depthM={depthM}
              explosives={explosives}
              nsiLengthOptions={nsiLengthOptions}
              detonatorDelayOptions={detonatorDelayOptions}
              initialInputs={variant.initialInputs}
              onInputsChange={variant.onInputsChange}
            />
          ))}
        </div>
        <div className="schemes">
          {variants.map((variant) =>
            variant.geometry ? (
              <HoleSchemeView
                key={variant.key}
                size="compact"
                idPrefix={`hs-${variant.key}`}
                hole={variant.geometry.hole}
                initiation={variant.geometry.initiation}
                crownMm={crownMm}
                title={variant.geometry.label}
              />
            ) : (
              <div key={variant.key} className="hole-scheme compact scheme-pending">Считаем…</div>
            ),
          )}
        </div>
        <div className="diff-block">
          <p className="block-caption">Отличаются между вариантами</p>
          {errors.map((variant) => (
            <div key={variant.key} className="page-error" role="alert">{variant.label}: {variant.error}</div>
          ))}
          {comparison ? (
            <div className="diff-tables">
              <DiffTable title="Скважина" rows={comparison.diffHole} variants={variants} />
              <DiffTable title="Блок" rows={comparison.diffBlock} variants={variants} />
            </div>
          ) : (
            <p className="page-caption">Считаем схемы заряда…</p>
          )}
        </div>
        <div className="shared-block">
          <p className="block-caption">Общее для обоих</p>
          {comparison && (
            <dl className="shared-list">
              {comparison.shared.map((row) => (
                <div key={row.label}>
                  <dt>{row.label}</dt>
                  <dd>{row.value}</dd>
                </div>
              ))}
            </dl>
          )}
        </div>
      </div>
    </section>
  );
}
