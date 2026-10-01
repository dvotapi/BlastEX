// Окно «Импорт чертежа» (TASK-013) — замена «Бровок из чертежа». Слева
// чертёж, справа шаги «Слои» и «Контур», внизу — «Построить блок» с ошибками
// и предупреждениями контура. Роли и повторный разбор сохраняются на сервере
// сразу: шаблон слоёв объекта должен пережить закрытие окна. Контур
// (кольцо, проверки, площади, свободную поверхность) считает сервер, окно
// показывает предпросмотр на каждое изменение.
import { useEffect, useMemo, useRef, useState, type MouseEvent, type SyntheticEvent } from "react";
import { api } from "../../../api/endpoints";
import { ruNumber } from "../../../lib/format";
import type {
  CadBench,
  CadContourLines,
  CadContourResult,
  CadLayerRoleCode,
  CadMeta,
  CadParams,
  CadRoleCode,
  CadRolesPayload,
  CadSource,
} from "../../../types/cad";
import type { CadContourInfo } from "../../../types/design";
import { BuildFooter } from "./BuildFooter";
import { applyRoleChanges } from "./cadRoles";
import { CadCanvas, type CanvasTarget } from "./CadCanvas";
import { CadImportHelp } from "./CadImportHelp";
import { polylineXY, SnapIndex, subPolyline, type XY } from "./contourGeometry";
import { ContourOverlay } from "./ContourOverlay";
import {
  applyPick,
  blockArea,
  contourRequest,
  initialContour,
  parseNumber,
  toleranceOf,
  type ContourState,
  type Pick,
} from "./contourState";
import { ContourStep } from "./ContourStep";
import { LayersStep } from "./LayersStep";
import { useContourPreview } from "./useContourPreview";

/** Что уходит в паспорт по «Построить блок»: контур по верхней бровке и данные чертежа. */
export type CadBuildChoice = {
  vertices: XY[];
  free_faces: number[][];
  bench: CadBench;
  cad: CadContourInfo;
};

export type CadImportDialogProps = {
  sources: CadSource[];
  /** Расстояние между рядами W паспорта — ширина блока «рядов × W». */
  burden: number | null;
  onSourcesChange: (sources: CadSource[]) => void;
  onCancel: () => void;
  onBuild: (choice: CadBuildChoice) => void;
};

type Tab = "layers" | "contour";

export function CadImportDialog({ sources, burden, onSourcesChange, onCancel, onBuild }: CadImportDialogProps) {
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
  const [tab, setTab] = useState<Tab>("layers");
  const [contour, setContour] = useState<ContourState>(() => (sources[0] ? initialContour(sources[0]) : initialContour({ entities: [] } as unknown as CadSource)));
  // Растёт, когда сервер пересчитал роли источника: тот же запрос контура даёт новый ответ.
  const [version, setVersion] = useState(0);
  const [lines, setLines] = useState<CadContourLines | null>(null);
  const [linesError, setLinesError] = useState("");
  const [floorText, setFloorText] = useState("");
  const [radiusText, setRadiusText] = useState("");
  const entities = useMemo(() => new Map((active?.entities ?? []).map((entity) => [entity.handle, entity])), [active?.entities]);
  const rolesKey = contour.roles.join(",");

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

  // Другой файл — свой контур, свой выбор и свои параметры разбора.
  useEffect(() => {
    if (!active) return;
    setContour(initialContour(active));
    setLines(null);
    setHover(null);
    setSelected(null);
    setExpanded(new Set());
    // В поле — только явно заданная подошва. Найденная в имени слоя — подсказка:
    // у каждого слоя «Горизонт …» она своя, и одна явная отметка их бы сравняла.
    setFloorText(active.params.floor_z_m === null ? "" : String(active.params.floor_z_m));
    setRadiusText(String(active.params.label_radius_m));
    // Пересчёт ролей того же файла не сбрасывает выбор: ключ — файл и масштаб.
  }, [active?.id, active?.params.scale]);

  function onBackdropClick(event: MouseEvent<HTMLDialogElement>) {
    if (event.target === ref.current) onCancel();
  }

  // React проводит `close` вложенного окна (справки) через родителей — окно
  // импорта закрывается только своим событием: Esc или «×» справки его не трогают.
  function onDialogClose(event: SyntheticEvent<HTMLDialogElement>) {
    if (event.target === ref.current) onCancel();
  }

  // Линии для контура: разрезы в пересечениях (участок по щелчку), сшитые
  // бровки и их разрывы. Зависят от ролей — после правки ролей перечитываются.
  useEffect(() => {
    if (!active) return;
    let alive = true;
    setLinesError("");
    api.cad
      .contourLines(active.id, contour.roles)
      .then((loaded) => alive && setLines(loaded))
      .catch((reason) => alive && setLinesError(reason instanceof Error ? reason.message : "Не удалось прочитать линии контура."));
    return () => {
      alive = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [active?.id, rolesKey, version]);

  const request = useMemo(() => contourRequest(contour, burden), [contour, burden]);
  const preview = useContourPreview(active?.id ?? "", active ? request : null, api.cad.contour, version);

  const snapIndex = useMemo(() => {
    if (tab !== "contour" || !active) return null;
    const roles: string[] = contour.method === "crest" ? ["crest_top"] : contour.roles;
    const candidates = active.entities.filter((entity) => entity.geometry_type === "line" && roles.includes(entity.role));
    return new SnapIndex(candidates, lines?.intersections ?? []);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tab, active?.entities, contour.method, rolesKey, lines]);

  // Подсветка выбранного на шаге «Контур»: готовая линия или участки сборки.
  const emphasized = useMemo(() => {
    if (tab !== "contour") return [];
    if (contour.method === "ready") return contour.handle ? [contour.handle] : [];
    if (contour.method === "assembly") return contour.items.filter((item) => item.kind === "part").map((item) => item.handle);
    return [];
  }, [tab, contour.method, contour.handle, contour.items]);

  const selectedPath = useMemo(() => {
    if (contour.method !== "assembly" || contour.selected === null) return null;
    const item = contour.items[contour.selected];
    if (!item) return null;
    if (item.kind !== "part") return item.points;
    const entity = entities.get(item.handle);
    return entity ? subPolyline(polylineXY(entity), item.start_m, item.end_m) : null;
  }, [contour.method, contour.selected, contour.items, entities]);

  const picks = [contour.pending?.point, contour.crestStart, contour.crestEnd].filter((point): point is XY => Boolean(point));

  function pick(target: Pick) {
    setContour((current) => applyPick(current, target, { entities, lines }));
  }

  /** Смена способа площади блока сохраняется на объекте работ — для следующих файлов. */
  function changeContour(next: ContourState) {
    if (active && next.areaBasis !== contour.areaBasis) {
      const source = active;
      onSourcesChange(sources.map((item) => (item.id === source.id ? { ...item, area_basis: next.areaBasis } : item)));
      api.cad
        .saveAreaBasis(source.id, next.areaBasis)
        .catch((reason) => setRequestError(reason instanceof Error ? reason.message : "Не удалось сохранить площадь блока."));
    }
    setContour(next);
  }

  function build(result: CadContourResult) {
    if (!active || !result.top) return;
    onBuild({
      vertices: result.top.points.map(([x, y]) => [x, y] as XY),
      free_faces: result.free_faces,
      bench: result.bench,
      cad: {
        source_id: active.id,
        file_name: active.file_name,
        method: result.method,
        items: result.items,
        top: result.top.points,
        bottom: result.bottom?.points ?? null,
        area_top_m2: result.top.area_m2,
        area_bottom_m2: result.bottom?.area_m2 ?? null,
        area_mean_m2: result.mean_area_m2,
        map_area_m2: parseNumber(contour.mapArea),
        area_basis: contour.areaBasis,
        area_m2: blockArea(result, contour.areaBasis),
        built_at: new Date().toISOString(),
        edited: false,
      },
    });
  }

  function replace(updated: CadSource) {
    onSourcesChange(sources.map((source) => (source.id === updated.id ? updated : source)));
    setVersion((current) => current + 1);
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
    // Ответ — без геометрии: роли сливаются в уже загруженный источник.
    const source = active;
    void run(async () => applyRoleChanges(source, await api.cad.saveRoles(source.id, payload)));
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
  const floorValue = parseNumber(floorText);
  const radiusValue = parseNumber(radiusText);
  const paramsChanged =
    params !== undefined &&
    (floorValue !== params.floor_z_m || (radiusValue !== null && radiusValue !== params.label_radius_m));

  return (
    <dialog
      ref={ref}
      className="cad-dialog"
      aria-labelledby="cad-dialog-title"
      onClose={onDialogClose}
      onClick={onBackdropClick}
    >
      <header>
        <b id="cad-dialog-title">Импорт чертежа</b>
        <span className="cad-files">{sources.map((source) => source.file_name).join(", ")}</span>
        <span className="cad-header-actions">
          <CadImportHelp meta={meta} />
        </span>
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
            emphasized={emphasized}
            onHover={setHover}
            onSelect={select}
            tool={tab === "contour"}
            snapIndex={snapIndex}
            snapMinM={toleranceOf(contour)}
            onPick={pick}
            overlay={
              tab === "contour"
                ? (toScreen) => (
                    <ContourOverlay
                      toScreen={toScreen}
                      result={preview.result}
                      gaps={lines?.gaps ?? []}
                      picks={picks}
                      selectedPath={selectedPath}
                    />
                  )
                : undefined
            }
          />
          <aside className="cad-panel">
            <div className="cad-steps" role="tablist" aria-label="Шаги импорта">
              <button type="button" role="tab" aria-selected={tab === "layers"} onClick={() => setTab("layers")}>
                Слои
              </button>
              <button type="button" role="tab" aria-selected={tab === "contour"} onClick={() => setTab("contour")}>
                Контур
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
            {tab === "layers" && (
              <>
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
                      placeholder={
                        active.floor_z_m !== null && active.params.floor_z_m === null
                          ? `из имени слоя: ${ruNumber(active.floor_z_m, 1)}`
                          : "из имени слоя"
                      }
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
                    : "Роли слоёв не сохранятся в шаблон объекта — причина в предупреждении выше."}
                  {pending && " Сохраняю…"}
                </p>
              </>
            )}
            {(requestError || metaError) && (
              <p className="cad-request-error" role="alert">
                {requestError || metaError}
              </p>
            )}
            {tab === "layers" ? (
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
            ) : (
              <div className="cad-contour-wrap">
                {meta ? (
                  <ContourStep
                    source={active}
                    meta={meta}
                    state={contour}
                    onChange={changeContour}
                    result={preview.result}
                    pending={preview.pending}
                    error={linesError}
                    burden={burden}
                    disabled={pending}
                    splitsError={lines?.splits_error ?? ""}
                  />
                ) : (
                  !metaError && <p className="cad-loading">Загружаю роли слоёв…</p>
                )}
              </div>
            )}
            <BuildFooter
              result={preview.result}
              pending={preview.pending}
              error={preview.error}
              areaLabel={meta?.area_bases.find((basis) => basis.code === contour.areaBasis)?.label ?? ""}
              onCancel={onCancel}
              onBuild={build}
            />
          </aside>
        </div>
      )}
    </dialog>
  );
}
