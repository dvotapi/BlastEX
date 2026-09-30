// «Построить блок» до шага «Контур» (TASK-013, PR 2): блок строится, как
// раньше, полосой между двумя выбранными линиями. Пара по умолчанию —
// самые длинные верхняя и нижняя бровки по ролям слоёв.
import { useMemo } from "react";
import { ruNumber } from "../../../lib/format";
import type { CadEntity } from "../../../types/cad";
import { benchCandidates } from "./legacyBuild";

const meanZ = (entity: CadEntity) => (entity.z_min + entity.z_max) / 2;

function optionLabel(entity: CadEntity): string {
  return `${entity.layer} · ${entity.handle} · ${ruNumber(entity.length_m, 0)} м · Z ${ruNumber(entity.z_min, 1)}…${ruNumber(entity.z_max, 1)}`;
}

export function LegacyBuildBlock({
  entities,
  crest,
  toe,
  busy,
  error,
  onChange,
  onCancel,
  onBuild,
}: {
  entities: CadEntity[];
  crest: string;
  toe: string;
  busy: boolean;
  error: string;
  onChange: (pair: { crest: string; toe: string }) => void;
  onCancel: () => void;
  onBuild: (pair: { crest: CadEntity; toe: CadEntity }) => void;
}) {
  // Сортировка всех линий — только при смене источника или выбора, не на наведение.
  const lines = useMemo(() => benchCandidates(entities, [crest, toe]), [entities, crest, toe]);
  const crestLine = lines.find((entity) => entity.handle === crest);
  const toeLine = lines.find((entity) => entity.handle === toe);
  const inverted = crestLine && toeLine && meanZ(crestLine) <= meanZ(toeLine);
  const ready = Boolean(crestLine && toeLine && crest !== toe) && !busy;

  const select = (label: "Верх" | "Низ", value: string, change: (value: string) => void) => (
    <label className="cad-build-field">
      <span>{label}</span>
      <select aria-label={label} value={value} disabled={busy} onChange={(event) => change(event.target.value)}>
        <option value="">— не выбрана —</option>
        {lines.map((entity) => (
          <option key={entity.handle} value={entity.handle}>
            {optionLabel(entity)}
          </option>
        ))}
      </select>
    </label>
  );

  return (
    <footer className="cad-build">
      <p className="cad-build-note">
        До шага «Контур» блок строится, как раньше, — полосой между верхней и нижней линией.
      </p>
      {select("Верх", crest, (value) => onChange({ crest: value, toe }))}
      {select("Низ", toe, (value) => onChange({ crest, toe: value }))}
      {inverted && <small className="cad-build-warning">Верх ниже низа — проверьте выбор линий.</small>}
      {error && (
        <small className="cad-build-error" role="alert">
          {error}
        </small>
      )}
      <div className="cad-build-actions">
        <button type="button" className="secondary-button" onClick={onCancel}>
          Отмена
        </button>
        <button
          type="button"
          className="primary-button"
          disabled={!ready}
          onClick={() => crestLine && toeLine && onBuild({ crest: crestLine, toe: toeLine })}
        >
          {busy ? "Строю…" : "Построить блок"}
        </button>
      </div>
    </footer>
  );
}
