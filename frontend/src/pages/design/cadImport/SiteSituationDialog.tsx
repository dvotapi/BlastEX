// «Ситуация объекта» (план 2026-11-13): план карьера — один на все блоки
// объекта. Файл грузится с назначением «ситуация»: у слоя только «Показывать»
// или нет и вид. Умолчания отбора считает сервер (дороги, объекты на
// поверхности и ЛЭП — всегда; скрытые в чертеже, другие блоки, сетки и
// отметки — нет); выбор человека запоминается на объекте, и следующий план
// приходит с тем же отбором.
import { useEffect, useMemo, useRef, useState, type MouseEvent, type SyntheticEvent } from "react";
import { api } from "../../../api/endpoints";
import { ruDate, ruDateTime } from "../../../lib/format";
import type {
  CadImportResponse,
  CadLayer,
  CadMeta,
  CadOrigin,
  CadRolesPayload,
  CadRolesResponse,
  CadSiteSources,
  CadSituationKind,
  CadSource,
  CadUploadParams,
} from "../../../types/cad";
import { CadCanvas, type CanvasTarget } from "./CadCanvas";

const DRAWING_ACCEPT = ".dxf,.dwg";
const ORIGIN_LABELS: Partial<Record<CadOrigin, string>> = { auto: "авто", template: "запомнено", manual: "вручную" };

export type SiteSituationDialogProps = {
  onClose: () => void;
  /** Отбор сохранён или загружен новый план — страница перечитывает ситуацию. */
  onChanged: () => void;
  /** Открыть этот план (из «Чертежей объекта»), а не самый свежий. */
  initialSource?: CadSource | null;
  list?: () => Promise<CadSiteSources>;
  load?: (id: string) => Promise<CadSource>;
  upload?: (files: File[], params: CadUploadParams) => Promise<CadImportResponse>;
  saveRoles?: (id: string, payload: CadRolesPayload) => Promise<CadRolesResponse>;
  loadMeta?: () => Promise<CadMeta>;
};

type Choice = { shown: Record<string, boolean>; kinds: Record<string, CadSituationKind> };

function choiceOf(layers: CadLayer[]): Choice {
  const shown: Record<string, boolean> = {};
  const kinds: Record<string, CadSituationKind> = {};
  for (const layer of layers) {
    shown[layer.name] = layer.role === "situation";
    kinds[layer.name] = layer.situation_kind ?? "other";
  }
  return { shown, kinds };
}

function message(reason: unknown, fallback: string): string {
  return reason instanceof Error && reason.message ? reason.message : fallback;
}

export function SiteSituationDialog({
  onClose,
  onChanged,
  initialSource = null,
  list = api.cad.siteSources,
  load = api.cad.source,
  upload = api.cad.upload,
  saveRoles = api.cad.saveRoles,
  loadMeta = api.cad.meta,
}: SiteSituationDialogProps) {
  const ref = useRef<HTMLDialogElement>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const [meta, setMeta] = useState<CadMeta | null>(null);
  const [source, setSource] = useState<CadSource | null>(initialSource);
  // Пока ищется текущий план объекта — «загрузка»; плана нет — форма загрузки.
  const [loading, setLoading] = useState(!initialSource);
  const [uploading, setUploading] = useState(false);
  const [replacing, setReplacing] = useState(false);
  const [noSite, setNoSite] = useState(false);
  const [surveyDate, setSurveyDate] = useState("");
  const [choice, setChoice] = useState<Choice>(() => choiceOf(initialSource?.layers ?? []));
  const [filter, setFilter] = useState("");
  const [hover, setHover] = useState<CanvasTarget | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    const dialog = ref.current;
    if (dialog && !dialog.open) dialog.showModal();
  }, []);

  useEffect(() => {
    let alive = true;
    loadMeta().then(
      (loaded) => alive && setMeta(loaded),
      () => undefined,
    );
    return () => {
      alive = false;
    };
  }, [loadMeta]);

  // Без заданного плана открывается самый свежий план карьера объекта.
  useEffect(() => {
    if (initialSource) return;
    let alive = true;
    list()
      .then(async (sources) => {
        if (!alive) return;
        if (!sources.site_code) {
          setNoSite(true);
          return;
        }
        const plan = sources.sources.find((item) => item.purpose === "situation");
        if (plan) {
          const loaded = await load(plan.id);
          if (alive) open(loaded);
        }
      })
      .catch((reason) => alive && setError(message(reason, "Не удалось найти ситуацию объекта.")))
      .finally(() => alive && setLoading(false));
    return () => {
      alive = false;
    };
    // Только при открытии окна.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function open(next: CadSource) {
    setSource(next);
    setChoice(choiceOf(next.layers));
    setReplacing(false);
    setSaved(false);
  }

  const layers = source?.layers ?? [];
  const server = useMemo(() => choiceOf(layers), [layers]);
  const dirty = layers.some(
    (layer) => choice.shown[layer.name] !== server.shown[layer.name] || choice.kinds[layer.name] !== server.kinds[layer.name],
  );
  const shownCount = layers.filter((layer) => choice.shown[layer.name]).length;
  const needle = filter.trim().toLocaleLowerCase("ru");
  const visible = needle ? layers.filter((layer) => layer.name.toLocaleLowerCase("ru").includes(needle)) : layers;

  // Холст: показанные слои и слой под курсором (чтобы увидеть, что включаешь).
  const canvasEntities = useMemo(() => {
    if (!source) return [];
    return source.entities
      .filter((entity) => entity.geometry_type !== "text" && (choice.shown[entity.layer] || hover?.layer === entity.layer))
      .map((entity) => ({ ...entity, role: choice.shown[entity.layer] ? "situation" : "ignore" }) as typeof entity);
  }, [source, choice.shown, hover?.layer]);

  function requestClose() {
    if (dirty && !window.confirm("Отбор слоёв не сохранён. Закрыть без сохранения?")) return;
    onClose();
  }

  function onDialogClose(event: SyntheticEvent<HTMLDialogElement>) {
    if (event.target === ref.current) onClose();
  }

  function onBackdropClick(event: MouseEvent<HTMLDialogElement>) {
    if (event.target === ref.current) requestClose();
  }

  async function onFile(file: File | undefined) {
    if (!file) return;
    if (fileRef.current) fileRef.current.value = "";
    setUploading(true);
    setError("");
    try {
      const response = await upload([file], { purpose: "situation", surveyDate: surveyDate || undefined });
      const loaded = response.sources[0];
      if (loaded) {
        open(loaded);
        onChanged();
      }
    } catch (reason) {
      setError(message(reason, "Не удалось загрузить план карьера."));
    } finally {
      setUploading(false);
    }
  }

  function setShown(names: string[], shown: boolean) {
    setChoice((current) => ({ ...current, shown: { ...current.shown, ...Object.fromEntries(names.map((name) => [name, shown])) } }));
    setSaved(false);
  }

  function setKind(name: string, kind: CadSituationKind) {
    setChoice((current) => ({ ...current, kinds: { ...current.kinds, [name]: kind } }));
    setSaved(false);
  }

  async function save() {
    if (!source) return;
    setBusy(true);
    setError("");
    try {
      // Все слои — выбор человека: следующий план объекта придёт с тем же отбором.
      const payload: CadRolesPayload = {
        layers: Object.fromEntries(layers.map((layer) => [layer.name, choice.shown[layer.name] ? "situation" : "ignore"])),
        kinds: Object.fromEntries(
          layers.filter((layer) => choice.kinds[layer.name] !== server.kinds[layer.name]).map((layer) => [layer.name, choice.kinds[layer.name]]),
        ),
      };
      const response = await saveRoles(source.id, payload);
      const next: CadSource = {
        ...source,
        layers: response.layers,
        warnings: response.warnings,
        entities: source.entities.map((entity) => {
          const changed = response.roles[entity.handle];
          return changed ? { ...entity, role: changed[0], role_origin: changed[1] } : entity;
        }),
      };
      setSource(next);
      setChoice(choiceOf(next.layers));
      setSaved(true);
      onChanged();
    } catch (reason) {
      setError(message(reason, "Не удалось сохранить отбор слоёв."));
    } finally {
      setBusy(false);
    }
  }

  const kindOptions = meta?.situation_kinds ?? [];
  const showUpload = !loading && (!source || replacing) && !noSite;

  return (
    <dialog
      ref={ref}
      className="cad-site-situation-dialog"
      aria-labelledby="cad-site-situation-title"
      onClose={onDialogClose}
      onClick={onBackdropClick}
      onCancel={(event) => {
        event.preventDefault();
        requestClose();
      }}
    >
      <header>
        <b id="cad-site-situation-title">Ситуация объекта</b>
        <button type="button" className="cad-close" aria-label="Закрыть" onClick={requestClose}>
          ×
        </button>
      </header>
      <p className="cad-sources-note">
        План карьера — один на все блоки объекта: документы блока без своей ситуации (паспорт на бурение, проект МВ,
        Г.5, схема постов) берут самый свежий план. Лишние слои снимите — выбор запомнится для следующего плана.
      </p>
      {error && (
        <p className="cad-request-error" role="alert">
          {error}
        </p>
      )}
      {loading && <p className="cad-loading">Ищу план карьера объекта…</p>}
      {noSite && (
        <p className="cad-sources-note">Объект работ не выбран — выберите объект в шапке: ситуация хранится на объекте.</p>
      )}
      {showUpload && (
        <div className="cad-site-situation-upload">
          <span>
            <b>{source ? "Новый план карьера" : "Плана карьера ещё нет"}</b>
            <small>DXF или DWG. Дата съёмки — из имени файла, если не задана.</small>
          </span>
          <label>
            Дата съёмки
            <input type="date" value={surveyDate} disabled={uploading} onChange={(event) => setSurveyDate(event.target.value)} />
          </label>
          <button type="button" className="primary-button" disabled={uploading} onClick={() => fileRef.current?.click()}>
            {uploading ? "Читаю…" : "Загрузить план"}
          </button>
          {source && (
            <button type="button" className="secondary-button" disabled={uploading} onClick={() => setReplacing(false)}>
              Отмена
            </button>
          )}
          <input
            ref={fileRef}
            type="file"
            accept={DRAWING_ACCEPT}
            hidden
            aria-label="Файл плана карьера"
            onChange={(event) => void onFile(event.target.files?.[0])}
          />
        </div>
      )}
      {source && !replacing && (
        <div className="cad-site-situation-body">
          <div className="cad-site-situation-source">
            <span>
              <b>{source.title}</b>
              <small>
                {source.survey_date ? `съёмка ${ruDate(source.survey_date)} · ` : ""}
                {source.file_name} · загружен {ruDateTime(source.uploaded_at)}
              </small>
            </span>
            <button type="button" className="secondary-button" disabled={busy} onClick={() => setReplacing(true)}>
              Загрузить новый план
            </button>
          </div>
          <div className="cad-site-situation-main">
            <div className="cad-site-situation-canvas">
              <CadCanvas
                entities={canvasEntities}
                fitKey={source.id}
                hover={hover}
                selected={null}
                emphasized={[]}
                onHover={setHover}
                onSelect={() => undefined}
              />
            </div>
            <div className="cad-site-situation-layers">
              <div className="cad-site-situation-tools">
                <input
                  type="search"
                  placeholder="Найти слой"
                  aria-label="Найти слой"
                  value={filter}
                  onChange={(event) => setFilter(event.target.value)}
                />
                <button type="button" className="secondary-button" onClick={() => setShown(visible.map((layer) => layer.name), true)}>
                  Показать все
                </button>
                <button type="button" className="secondary-button" onClick={() => setShown(visible.map((layer) => layer.name), false)}>
                  Снять все
                </button>
              </div>
              <small className="cad-sources-note">
                Показано слоёв: {shownCount} из {layers.length}
                {needle ? ` · найдено ${visible.length}` : ""}
              </small>
              <table className="cad-site-situation-table">
                <thead>
                  <tr>
                    <th scope="col">
                      <span className="sr-only">Показывать</span>
                    </th>
                    <th scope="col">Слой</th>
                    <th scope="col">Вид</th>
                    <th scope="col" title="Объектов в слое">Объектов</th>
                  </tr>
                </thead>
                <tbody>
                  {visible.map((layer) => (
                    <tr
                      key={layer.name}
                      className={hover?.layer === layer.name ? "is-hover" : undefined}
                      onMouseEnter={() => setHover({ layer: layer.name, handle: null })}
                      onMouseLeave={() => setHover(null)}
                    >
                      <td>
                        <input
                          type="checkbox"
                          aria-label={`Показывать слой «${layer.name}»`}
                          checked={Boolean(choice.shown[layer.name])}
                          onChange={(event) => setShown([layer.name], event.target.checked)}
                        />
                      </td>
                      <td className="cad-site-situation-name" title={layer.name}>
                        {layer.name}
                        {layer.hidden && <span className="cad-site-situation-badge">скрыт в чертеже</span>}
                        {ORIGIN_LABELS[layer.origin] && (
                          <span className="cad-site-situation-origin">{ORIGIN_LABELS[layer.origin]}</span>
                        )}
                      </td>
                      <td>
                        <select
                          aria-label={`Вид слоя «${layer.name}»`}
                          value={choice.kinds[layer.name] ?? "other"}
                          onChange={(event) => setKind(layer.name, event.target.value as CadSituationKind)}
                        >
                          {kindOptions.map((kind) => (
                            <option key={kind.code} value={kind.code}>
                              {kind.label}
                            </option>
                          ))}
                        </select>
                      </td>
                      <td className="cad-sources-count">{layer.entity_count}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
          <footer className="cad-site-situation-footer">
            {saved && !dirty && <span className="cad-site-situation-saved">Отбор сохранён и запомнен для объекта.</span>}
            <button type="button" className="primary-button" disabled={busy || !dirty} onClick={() => void save()}>
              {busy ? "Сохраняю…" : "Сохранить отбор"}
            </button>
          </footer>
        </div>
      )}
    </dialog>
  );
}
