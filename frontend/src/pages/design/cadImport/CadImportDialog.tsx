// Окно «Импорт чертежа» (TASK-013) — замена «Бровок из чертежа». Слева
// чертёж, справа шаги; пока есть шаг «Слои», построение — прежнее, полосой
// между двумя линиями. Роли и повторный разбор сохраняются на сервере сразу:
// шаблон слоёв объекта должен пережить закрытие окна.
import { useEffect, useRef, useState, type MouseEvent } from "react";
import { api } from "../../../api/endpoints";
import { ruNumber } from "../../../lib/format";
import type { CadEntity, CadLayerRoleCode, CadMeta, CadParams, CadRoleCode, CadRolesPayload, CadSource } from "../../../types/cad";
import { CadCanvas, type CanvasTarget } from "./CadCanvas";
import { LayersStep } from "./LayersStep";
import { LegacyBuildBlock } from "./LegacyBuildBlock";
import { defaultBenchPair } from "./legacyBuild";

export type CadBuildChoice = { crest: CadEntity; toe: CadEntity; fileName: string };

export type CadImportDialogProps = {
  sources: CadSource[];
  busy: boolean;
  error: string;
  onSourcesChange: (sources: CadSource[]) => void;
  onCancel: () => void;
  onBuild: (choice: CadBuildChoice) => void;
};

function numberOrNull(text: string): number | null {
  const value = Number(text.replace(",", ".").trim());
  return text.trim() && Number.isFinite(value) ? value : null;
}

export function CadImportDialog({ sources, busy, error, onSourcesChange, onCancel, onBuild }: CadImportDialogProps) {
  const ref = useRef<HTMLDialogElement>(null);
  const [meta, setMeta] = useState<CadMeta | null>(null);
  const [metaError, setMetaError] = useState("");
  const [activeId, setActiveId] = useState(sources[0]?.id ?? "");
  const [hover, setHover] = useState<CanvasTarget | null>(null);
  const [selected, setSelected] = useState<CanvasTarget | null>(null);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [pending, setPending] = useState(false);
  const [requestError, setRequestError] = useState("");
  const active = sources.find((source) => source.id === activeId) ?? sources[0];
  const [pair, setPair] = useState(() => defaultBenchPair(active?.entities ?? []));
  const [floorText, setFloorText] = useState("");
  const [radiusText, setRadiusText] = useState("");

  useEffect(() => {
    const dialog = ref.current;
    if (dialog && !dialog.open) dialog.showModal();
  }, []);

  useEffect(() => {
    let alive = true;
    api.cad
      .meta()
      .then((loaded) => alive && setMeta(loaded))
      .catch((reason) => alive && setMetaError(reason instanceof Error ? reason.message : "Не удалось загрузить роли слоёв."));
    return () => {
      alive = false;
    };
  }, []);

  // Другой файл — своя пара бровок, свой выбор и свои параметры разбора.
  useEffect(() => {
    if (!active) return;
    setPair(defaultBenchPair(active.entities));
    setHover(null);
    setSelected(null);
    setExpanded(new Set());
    setFloorText(active.floor_z_m === null ? "" : String(active.floor_z_m));
    setRadiusText(String(active.params.label_radius_m));
    // Пересчёт ролей того же файла не сбрасывает выбор: ключ — файл и масштаб.
  }, [active?.id, active?.params.scale]);

  function onBackdropClick(event: MouseEvent<HTMLDialogElement>) {
    if (event.target === ref.current) onCancel();
  }

  function replace(updated: CadSource) {
    onSourcesChange(sources.map((source) => (source.id === updated.id ? updated : source)));
  }

  async function run(action: () => Promise<CadSource>) {
    setPending(true);
    setRequestError("");
    try {
      replace(await action());
    } catch (reason) {
      setRequestError(reason instanceof Error ? reason.message : "Не удалось сохранить изменения.");
    } finally {
      setPending(false);
    }
  }

  function saveRoles(payload: CadRolesPayload) {
    if (!active) return;
    void run(() => api.cad.saveRoles(active.id, payload));
  }

  function reparse(patch: Partial<CadParams>) {
    if (!active) return;
    void run(() => api.cad.reparse(active.id, { ...active.params, ...patch }));
  }

  function select(target: CanvasTarget) {
    setSelected(target);
    if (!target.handle) return;
    setExpanded((current) => new Set(current).add(target.layer));
    // Строка появится после раскрытия слоя — прокручиваем к ней в следующем кадре.
    requestAnimationFrame(() => {
      document
        .querySelector(`.cad-entity-row[data-handle="${CSS.escape(target.handle ?? "")}"]`)
        ?.scrollIntoView({ block: "nearest" });
    });
  }

  function toggle(layer: string) {
    setExpanded((current) => {
      const next = new Set(current);
      if (next.has(layer)) next.delete(layer);
      else next.add(layer);
      return next;
    });
  }

  const params = active?.params;
  const floorValue = numberOrNull(floorText);
  const radiusValue = numberOrNull(radiusText);
  const paramsChanged =
    params !== undefined &&
    (floorValue !== active?.floor_z_m || (radiusValue !== null && radiusValue !== params.label_radius_m));

  return (
    <dialog
      ref={ref}
      className="cad-dialog"
      aria-labelledby="cad-dialog-title"
      onClose={onCancel}
      onClick={onBackdropClick}
    >
      <header>
        <b id="cad-dialog-title">Импорт чертежа</b>
        <span className="cad-files">{sources.map((source) => source.file_name).join(", ")}</span>
        <button type="button" className="cad-close" aria-label="Закрыть" onClick={onCancel}>
          ×
        </button>
      </header>
      {active && (
        <div className="cad-dialog-body">
          <CadCanvas
            entities={active.entities}
            fitKey={`${active.id}:${active.params.scale}`}
            hover={hover}
            selected={selected}
            emphasized={[pair.crest, pair.toe].filter(Boolean)}
            onHover={setHover}
            onSelect={select}
          />
          <aside className="cad-panel">
            <div className="cad-steps" role="tablist" aria-label="Шаги импорта">
              <button type="button" role="tab" aria-selected="true">
                Слои
              </button>
            </div>
            {sources.length > 1 && (
              <label className="cad-source-picker">
                <span>Файл</span>
                <select value={active.id} onChange={(event) => setActiveId(event.target.value)}>
                  {sources.map((source) => (
                    <option key={source.id} value={source.id}>
                      {source.file_name}
                    </option>
                  ))}
                </select>
              </label>
            )}
            {active.warnings.length > 0 && (
              <ul className="cad-warnings">
                {active.warnings.map((warning) => (
                  <li key={`${warning.code}:${warning.message}`} className={`cad-warning level-${warning.level}`}>
                    {warning.message}
                  </li>
                ))}
              </ul>
            )}
            {(active.suggested_scale !== null || active.params.scale !== 1) && (
              <div className="cad-scale-actions">
                {active.suggested_scale !== null && (
                  <button
                    type="button"
                    className="secondary-button"
                    disabled={pending}
                    onClick={() => reparse({ scale: active.suggested_scale ?? 1 })}
                  >
                    Применить масштаб {ruNumber(active.suggested_scale, 3)}
                  </button>
                )}
                {active.params.scale !== 1 && (
                  <button type="button" className="secondary-button" disabled={pending} onClick={() => reparse({ scale: 1 })}>
                    Вернуть масштаб 1
                  </button>
                )}
              </div>
            )}
            <div className="cad-params">
              <label>
                <span>Подошва, м</span>
                <input
                  inputMode="decimal"
                  value={floorText}
                  placeholder="из имени слоя"
                  disabled={pending}
                  onChange={(event) => setFloorText(event.target.value)}
                />
              </label>
              <label>
                <span>Радиус подписи, м</span>
                <input
                  inputMode="decimal"
                  value={radiusText}
                  disabled={pending}
                  onChange={(event) => setRadiusText(event.target.value)}
                />
              </label>
              <button
                type="button"
                className="secondary-button"
                disabled={pending || !paramsChanged}
                onClick={() => reparse({ floor_z_m: floorValue, label_radius_m: radiusValue ?? params?.label_radius_m ?? 3 })}
              >
                Пересчитать
              </button>
            </div>
            <p className="cad-template">
              {active.template_saved
                ? `Роли слоёв сохраняются в шаблон объекта «${active.work_object_name}».`
                : "Шаблон объекта не сохранится — выберите объект работ."}
              {pending && " Сохраняю…"}
            </p>
            {(requestError || metaError) && (
              <p className="cad-request-error" role="alert">
                {requestError || metaError}
              </p>
            )}
            <div className="cad-layers-wrap">
              {meta ? (
                <LayersStep
                  source={active}
                  meta={meta}
                  hover={hover}
                  selected={selected}
                  expanded={expanded}
                  disabled={pending}
                  onToggle={toggle}
                  onHover={setHover}
                  onSelect={select}
                  onLayerRole={(layer: string, role: CadLayerRoleCode) => saveRoles({ layers: { [layer]: role } })}
                  onEntityRole={(handle: string, role: CadRoleCode | null) => saveRoles({ entities: { [handle]: role } })}
                />
              ) : (
                !metaError && <p className="cad-loading">Загружаю роли слоёв…</p>
              )}
            </div>
            <LegacyBuildBlock
              entities={active.entities}
              crest={pair.crest}
              toe={pair.toe}
              busy={busy}
              error={error}
              onChange={setPair}
              onCancel={onCancel}
              onBuild={({ crest, toe }) => onBuild({ crest, toe, fileName: active.file_name })}
            />
          </aside>
        </div>
      )}
    </dialog>
  );
}
