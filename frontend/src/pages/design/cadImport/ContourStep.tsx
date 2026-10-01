// Шаг «Контур» окна «Импорт чертежа» (TASK-013, PR 2): четыре способа
// получить контур блока, площади обоих контуров и сверка с блоковой картой.
// Контур, проверки и площади считает сервер; здесь — поля способа, а щелчки
// по чертежу приходят из холста (`contourState.applyPick`).
import { ruNumber } from "../../../lib/format";
import type { CadContourResult, CadCrestSide, CadMeta, CadRoleCode, CadSource } from "../../../types/cad";
import { AssemblyList } from "./AssemblyList";
import {
  asAssembly,
  flipItem,
  parseNumber,
  readyCandidates,
  removeItem,
  toleranceOf,
  undoItem,
  widthMeters,
  type AssemblyTool,
  type ContourState,
} from "./contourState";

export type ContourStepProps = {
  source: CadSource;
  meta: CadMeta;
  state: ContourState;
  onChange: (next: ContourState) => void;
  result: CadContourResult | null;
  pending: boolean;
  error: string;
  /** Расстояние между рядами W из паспорта — для ширины «рядов × W». */
  burden: number | null;
  disabled: boolean;
  /** Разрезы линий не посчитаны: мешает только щелчку внутри и сборке. */
  splitsError?: string;
};

const METHODS: Array<{ code: ContourState["method"]; label: string }> = [
  { code: "ready", label: "Готовый" },
  { code: "click", label: "Щелчок внутри" },
  { code: "assembly", label: "Сборка" },
  { code: "crest", label: "Блок по бровке" },
];

const TOOLS: Array<{ code: AssemblyTool; label: string; hint: string }> = [
  { code: "piece", label: "Участок", hint: "Щелчок по линии добавляет её кусок между соседними пересечениями." },
  { code: "points", label: "По точкам", hint: "Два щелчка на одной линии — кусок между ними." },
  { code: "segment", label: "Отрезок", hint: "Две точки с привязкой — прямой отрезок от вершины к вершине." },
];

const SIDES: Array<{ code: CadCrestSide; label: string }> = [
  { code: "auto", label: "авто — от нижней бровки" },
  { code: "left", label: "слева по ходу" },
  { code: "right", label: "справа по ходу" },
];

function area(value: number | null | undefined): string {
  return value === null || value === undefined ? "—" : `${ruNumber(value, 1)} м²`;
}

function deviation(value: number | null | undefined, map: number | null): string {
  if (value === null || value === undefined || map === null || map <= 0) return "";
  const percent = ((value - map) / map) * 100;
  return ` (${percent > 0 ? "+" : ""}${ruNumber(percent, 2)} %)`;
}

function RoleChecks({ meta, state, onChange, disabled }: Pick<ContourStepProps, "meta" | "state" | "onChange" | "disabled">) {
  const lineRoles = meta.roles.filter((role) => role.applies_to.includes("line") && role.code !== "ignore");
  function toggle(code: CadRoleCode) {
    const roles = state.roles.includes(code) ? state.roles.filter((role) => role !== code) : [...state.roles, code];
    onChange({ ...state, roles });
  }
  return (
    <fieldset className="cad-contour-roles" disabled={disabled}>
      <legend>Линии контура</legend>
      {lineRoles.map((role) => (
        <label key={role.code}>
          <input
            type="checkbox"
            checked={state.roles.includes(role.code as CadRoleCode)}
            onChange={() => toggle(role.code as CadRoleCode)}
          />
          {role.label}
        </label>
      ))}
    </fieldset>
  );
}

export function ContourStep(props: ContourStepProps) {
  const { source, meta, state, onChange, result, pending, error, burden, disabled, splitsError = "" } = props;
  const linesNote = splitsError && (state.method === "click" || state.method === "assembly") ? (
    <p className="cad-request-error" role="alert">
      {splitsError}
    </p>
  ) : null;
  const set = (patch: Partial<ContourState>) => onChange({ ...state, ...patch });
  const map = parseNumber(state.mapArea);
  const reached = result?.flanks.filter((flank) => flank.length_m !== null) ?? [];

  return (
    <div className="cad-contour">
      <div className="cad-methods" role="radiogroup" aria-label="Способ контура">
        {METHODS.map((method) => (
          <button
            key={method.code}
            type="button"
            role="radio"
            aria-checked={state.method === method.code}
            disabled={disabled}
            onClick={() => set({ method: method.code, pending: null })}
          >
            {method.label}
          </button>
        ))}
      </div>

      {state.method === "ready" && (
        <div className="cad-contour-panel">
          <label className="cad-contour-field">
            <span>Замкнутая линия</span>
            <select value={state.handle} disabled={disabled} onChange={(event) => set({ handle: event.target.value })}>
              <option value="">— не выбрана —</option>
              {readyCandidates(source.entities, toleranceOf(state)).map((entity) => (
                <option key={entity.handle} value={entity.handle}>
                  {`${entity.layer} · ${entity.handle} · ${ruNumber(entity.area_m2, 0)} м²`}
                </option>
              ))}
            </select>
          </label>
          <p className="cad-hint">Линию можно выбрать и щелчком по ней на чертеже. Почти замкнутая (разрыв не больше допуска) замыкается сама.</p>
        </div>
      )}

      {state.method === "click" && (
        <div className="cad-contour-panel">
          <p className="cad-hint">Щёлкните внутри области на чертеже — как штриховка в AutoCAD.</p>
          <RoleChecks meta={meta} state={state} onChange={onChange} disabled={disabled} />
          {linesNote}
          <label className="cad-contour-field">
            <span>Мост до, м</span>
            <input inputMode="decimal" value={state.bridge} disabled={disabled} onChange={(event) => set({ bridge: event.target.value })} />
          </label>
        </div>
      )}

      {state.method === "assembly" && (
        <div className="cad-contour-panel">
          <div className="cad-tools" role="radiogroup" aria-label="Инструмент сборки">
            {TOOLS.map((tool) => (
              <button
                key={tool.code}
                type="button"
                role="radio"
                aria-checked={state.tool === tool.code}
                disabled={disabled}
                onClick={() => set({ tool: tool.code, pending: null })}
              >
                {tool.label}
              </button>
            ))}
          </div>
          <p className="cad-hint">
            {TOOLS.find((tool) => tool.code === state.tool)?.hint} Направление участка выбирается по ближайшему концу.
            {state.pending && " Первая точка отмечена."}
          </p>
          <RoleChecks meta={meta} state={state} onChange={onChange} disabled={disabled} />
          {linesNote}
          <div className="cad-assembly-wrap">
            {state.items.length ? (
              <AssemblyList
                items={state.items}
                info={result?.method === "assembly" && !pending ? result.item_info : []}
                selected={state.selected}
                onSelect={(index) => set({ selected: index })}
              />
            ) : (
              <p className="cad-hint">Участков пока нет.</p>
            )}
          </div>
          <div className="cad-assembly-actions">
            <button type="button" className="secondary-button" disabled={disabled || (!state.items.length && !state.pending)} onClick={() => onChange(undoItem(state))}>
              Отменить
            </button>
            <button
              type="button"
              className="secondary-button"
              disabled={disabled || state.selected === null}
              onClick={() => state.selected !== null && onChange(flipItem(state, state.selected))}
            >
              Развернуть
            </button>
            <button
              type="button"
              className="secondary-button"
              disabled={disabled || state.selected === null}
              onClick={() => state.selected !== null && onChange(removeItem(state, state.selected))}
            >
              Удалить
            </button>
            <button type="button" className="secondary-button" disabled={disabled || !state.items.length} onClick={() => set({ items: [], selected: null, pending: null })}>
              Очистить
            </button>
          </div>
        </div>
      )}

      {state.method === "crest" && (
        <div className="cad-contour-panel">
          <p className="cad-hint">
            Отметьте на чертеже начало и конец блока на верхней бровке.{" "}
            {state.crestStart ? (state.crestEnd ? "Обе точки отмечены." : "Начало отмечено.") : ""}
          </p>
          <div className="cad-width">
            <label>
              <input type="radio" checked={state.widthMode === "meters"} disabled={disabled} onChange={() => set({ widthMode: "meters" })} />
              Ширина, м
            </label>
            <input
              aria-label="Ширина, м"
              inputMode="decimal"
              value={state.width}
              disabled={disabled || state.widthMode !== "meters"}
              onChange={(event) => set({ width: event.target.value })}
            />
            <label>
              <input type="radio" checked={state.widthMode === "rows"} disabled={disabled} onChange={() => set({ widthMode: "rows" })} />
              Рядов × W
            </label>
            <input
              aria-label="Рядов"
              inputMode="numeric"
              value={state.rows}
              disabled={disabled || state.widthMode !== "rows"}
              onChange={(event) => set({ rows: event.target.value })}
            />
          </div>
          {state.widthMode === "rows" && (
            <p className="cad-hint">
              {burden !== null && burden > 0
                ? `× W ${ruNumber(burden, 1)} м = ${ruNumber(widthMeters(state, burden), 1)} м`
                : "Расстояние между рядами W в паспорте не задано — задайте ширину в метрах."}
            </p>
          )}
          <label className="cad-contour-field">
            <span>Сторона блока</span>
            <select value={state.side} disabled={disabled} onChange={(event) => set({ side: event.target.value as CadCrestSide })}>
              {SIDES.map((side) => (
                <option key={side.code} value={side.code}>
                  {side.label}
                </option>
              ))}
            </select>
          </label>
        </div>
      )}

      <div className="cad-contour-common">
        <label className="cad-contour-field">
          <span>Допуск, м</span>
          <input inputMode="decimal" value={state.tolerance} disabled={disabled} onChange={(event) => set({ tolerance: event.target.value })} />
        </label>
        {result && result.items.length > 0 && state.method !== "assembly" && (
          <button type="button" className="secondary-button" disabled={disabled} onClick={() => onChange(asAssembly(state, result))}>
            Править как сборку
          </button>
        )}
      </div>

      <dl className="cad-areas" role="group" aria-label="Площади">
        <dt>S верх</dt>
        <dd>
          {area(result?.top?.area_m2)}
          {deviation(result?.top?.area_m2, map)}
        </dd>
        <dt>S низ</dt>
        <dd>
          {area(result?.bottom?.area_m2)}
          {deviation(result?.bottom?.area_m2, map)}
        </dd>
        <dt>S ср</dt>
        <dd>
          {area(result?.mean_area_m2)}
          {deviation(result?.mean_area_m2, map)}
        </dd>
        <dt>Периметр</dt>
        <dd>{result?.top ? `${ruNumber(result.top.perimeter_m, 1)} м` : "—"}</dd>
        <dt>
          <label htmlFor="cad-map-area">S с карты, м²</label>
        </dt>
        <dd>
          <input
            id="cad-map-area"
            inputMode="decimal"
            placeholder="с блоковой карты"
            value={state.mapArea}
            disabled={disabled}
            onChange={(event) => set({ mapArea: event.target.value })}
          />
        </dd>
      </dl>
      {reached.length > 0 && (
        <p className="cad-hint">
          Фланги продлены до нижней бровки: {reached.map((flank) => ruNumber(flank.length_m, 1)).join(" и ")} м.
        </p>
      )}
      {pending && <p className="cad-hint">Считаю контур…</p>}
      {error && (
        <p className="cad-request-error" role="alert">
          {error}
        </p>
      )}
    </div>
  );
}
