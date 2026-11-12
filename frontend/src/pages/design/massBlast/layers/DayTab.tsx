// Вкладка «День взрыва» окна проекта МВ (TASK-018, PR 6, §6): слои —
// документы дня взрыва. Какие слои можно открыть — решает сервер
// (`GET …/layers/available`); перенос заново показывает расхождение до
// подтверждения; выпуск — неизменяемая ревизия слоя.
import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../../../../api/endpoints";
import type {
  LayerAvailability,
  LayerChange,
  LayerKind,
  MassBlastLayer,
  MassBlastProjectV2,
  NotificationAddressees,
} from "../../../../types/massBlast";
import { sameAsReference } from "../form";
import { download, errorText, Issues, openPdf, type RememberControl } from "../ui";
import { draftFromPayload, LAYER_FORMS, payloadFromDraft, type LayerDraft } from "./LayerForms";

const ORDER: LayerKind[] = ["NARYAD", "NOTIFICATION", "READINESS_ACT", "TALON", "ACCEPTANCE_ACT", "EXECUTION"];
const REFRESH_CODES = new Set(["layer_stale", "fact_changed", "fact_layer_stale"]);
const AFTER_BLAST = new Set(["executed", "closed"]);
const isConflict = (reason: unknown) => (reason as { status?: number } | null)?.status === 409;

function LayerCard({
  layer,
  label,
  projectStatus,
  onChange,
  onIssued,
  onDirty,
  canRemember,
}: {
  layer: MassBlastLayer;
  label: string;
  projectStatus: MassBlastProjectV2["lifecycle_status"];
  onChange: (layer: MassBlastLayer) => void;
  /** Выпуск ревизии меняет и другие слои (новая ревизия «Факта» — `fact_layer_stale` у наряда и акта приёмки). */
  onIssued: () => Promise<void>;
  /** Есть ли у карточки несохранённые правки — окно спросит перед закрытием. */
  onDirty: (layerId: string, dirty: boolean) => void;
  /** Может ли пользователь писать в справочник объекта (В8). */
  canRemember: boolean;
}) {
  const [rememberChoice, setRememberChoice] = useState<Record<string, boolean>>({});
  const [draft, setDraft] = useState<LayerDraft>(() => draftFromPayload(layer));
  const [dirty, setDirty] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ text: string; error: boolean } | null>(null);
  const [changes, setChanges] = useState<LayerChange[] | null>(null);
  const [revisionNo, setRevisionNo] = useState<number | null>(null);
  const { payload, errors } = payloadFromDraft(layer.kind, draft);
  const hasInputErrors = Object.keys(errors).length > 0;
  const needsRefresh = layer.stale || layer.issues.some((issue) => REFRESH_CODES.has(issue.code));
  const blocking = layer.issues.some((issue) => issue.level === "error");
  const Form = LAYER_FORMS[layer.kind];

  // Новая основа формы — только когда слой действительно изменился (сохранение,
  // перенос, выпуск): перечитанный список слоёв с той же версией (открыли другой
  // слой) несохранённые правки этой карточки не стирает.
  useEffect(() => {
    setDraft(draftFromPayload(layer));
    setDirty(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [layer.id, layer.version, layer.status, layer.current_revision_id]);

  useEffect(() => {
    onDirty(layer.id, dirty);
  }, [dirty, layer.id, onDirty]);
  useEffect(() => () => onDirty(layer.id, false), [layer.id, onDirty]);

  function set(key: string, value: unknown) {
    setDraft((current) => ({ ...current, [key]: value }));
    setDirty(true);
  }

  /** «Запомнить для объекта» у поля слоя (В8): заполненное, другое, чем в справочнике. */
  function remember(name: string, own: string): RememberControl | null {
    const fields = ((layer.view ?? {}).rememberable ?? {}) as Record<string, unknown>;
    if (!canRemember || !(name in fields) || !own.trim()) return null;
    const reference = fields[name];
    if (sameAsReference(own, reference)) return null;
    const empty = reference === null || reference === undefined || reference === "";
    return {
      checked: rememberChoice[name] ?? empty,
      onChange: (checked) => setRememberChoice((current) => ({ ...current, [name]: checked })),
    };
  }

  async function save(): Promise<MassBlastLayer | null> {
    if (!dirty) return layer;
    if (hasInputErrors) {
      setMessage({ text: "Исправьте числа в форме слоя.", error: true });
      return null;
    }
    const fields = Object.keys(((layer.view ?? {}).rememberable ?? {}) as Record<string, unknown>);
    const remembered = fields.filter((name) => remember(name, String(payload[name] ?? ""))?.checked);
    const saved = await api.massBlast.saveLayer(layer.id, { payload, expected_version: layer.version });
    if (remembered.length) {
      await api.massBlast.remember(saved.project_id, { paths: remembered, layer_id: saved.id });
      setRememberChoice({});
      // Справочник изменился — поля «запомнить» и значения по умолчанию слоя тоже.
      onChange(await api.massBlast.getLayer(saved.id));
      return saved;
    }
    onChange(saved);
    return saved;
  }

  async function run(action: () => Promise<void>, fallback: string) {
    setBusy(true);
    setMessage(null);
    try {
      await action();
    } catch (reason) {
      setMessage({
        text: isConflict(reason) ? "Слой изменён в другом окне. Закройте и откройте проект заново." : errorText(reason, fallback),
        error: true,
      });
    } finally {
      setBusy(false);
    }
  }

  const onSave = () => run(async () => {
    if (await save()) setMessage({ text: "Сохранено.", error: false });
  }, "Не удалось сохранить слой.");

  const onPreview = () => run(async () => {
    await openPdf(async () => {
      const saved = await save();
      return saved ? api.massBlast.layerPreviewUrl(saved.id) : null;
    });
  }, "Предпросмотр недоступен.");

  const onIssue = () => run(async () => {
    const saved = await save();
    if (!saved) return;
    const revision = await api.massBlast.issueLayer(saved.id, { expected_version: saved.version });
    setRevisionNo(revision.revision_no);
    // Весь список: у зависимых слоёв появляются замечания и «Перенести данные заново»;
    // их несохранённые правки не стираются (версия у них прежняя).
    await onIssued();
    setMessage({ text: `Выпущена ревизия слоя № ${revision.revision_no}.`, error: false });
  }, "Не удалось выпустить ревизию слоя.");

  const onDownload = () => run(async () => {
    if (!layer.current_revision_id) return;
    const warning = await download(api.massBlast.layerDocumentUrl(layer.current_revision_id), `${layer.kind.toLowerCase()}.pdf`);
    if (warning) setMessage({ text: warning, error: false });
  }, "Не удалось скачать документ слоя.");

  const onRefresh = () => run(async () => {
    const saved = await save();
    if (!saved) return;
    const result = await api.massBlast.refreshLayer(saved.id, { expected_version: saved.version, confirm: false });
    setChanges(result.changes);
    if (!result.changes.length) setMessage({ text: "Данные проекта не изменились — переносить нечего.", error: false });
  }, "Не удалось получить расхождение.");

  const onConfirm = () => run(async () => {
    // Правки, сделанные, пока было открыто расхождение, сначала сохраняются:
    // перенос меняет версию слоя, и несохранённая форма иначе пропала бы.
    const saved = await save();
    if (!saved) return;
    const result = await api.massBlast.refreshLayer(saved.id, { expected_version: saved.version, confirm: true });
    setChanges(null);
    onChange(result.layer);
    setMessage({ text: "Данные проекта перенесены заново; введённое вручную сохранено.", error: false });
  }, "Не удалось перенести данные.");

  return (
    <fieldset className="mb-layer">
      <legend>{label}</legend>
      <small className="drill-hint">
        {layer.status === "issued" ? `Выпущен${revisionNo ? `, ревизия № ${revisionNo}` : ""}` : "Черновик"}
        {layer.stale ? " · устарел: проект перевыпущен" : ""}
        {dirty ? " · есть несохранённые правки" : ""}
      </small>
      <Form layer={layer} draft={draft} set={set} disabled={busy} errors={errors} afterBlast={AFTER_BLAST.has(projectStatus)} remember={remember} />
      <Issues issues={layer.issues} />
      {changes && changes.length > 0 && (
        <div className="mb-diff">
          <b>Что изменится при переносе</b>
          <table className="drill-check" aria-label="Расхождение переноса">
            <thead><tr><th>Что</th><th>Было</th><th>Станет</th></tr></thead>
            <tbody>
              {changes.map((change, index) => (
                <tr key={index}>
                  <th scope="row">{change.label}</th>
                  <td>{change.before_text}</td>
                  <td>{change.after_text}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <small className="drill-hint">Введённое вручную (запас, номера, время, подписанты, адресат) сохранится.</small>
          <div className="plans-actions">
            <button type="button" className="calculate-button" disabled={busy} onClick={() => void onConfirm()}>Подтвердить перенос</button>
            <button type="button" className="secondary-button" disabled={busy} onClick={() => setChanges(null)}>Отмена</button>
          </div>
        </div>
      )}
      <div className="plans-actions">
        <button type="button" className="secondary-button" disabled={busy || !dirty} onClick={() => void onSave()}>Сохранить</button>
        <button type="button" className="secondary-button" disabled={busy || (!dirty && blocking)} onClick={() => void onPreview()}>Предпросмотр</button>
        <button type="button" className="calculate-button" disabled={busy || (!dirty && blocking)} onClick={() => void onIssue()}>Выпустить ревизию</button>
        {layer.current_revision_id && (
          <button type="button" className="secondary-button" disabled={busy} onClick={() => void onDownload()}>Скачать PDF</button>
        )}
        {needsRefresh && (
          <button type="button" className="secondary-button" disabled={busy} onClick={() => void onRefresh()}>Перенести данные заново</button>
        )}
      </div>
      {message && <small className={message.error ? "form-error" : "drill-message"}>{message.text}</small>}
    </fieldset>
  );
}

/** Подпись карточки: у уведомления — адресат, у нескольких нарядов — номер. */
function cardLabel(layer: MassBlastLayer, label: string, number: number): string {
  if (layer.kind === "NOTIFICATION") {
    const addressee = (layer.view.addressee ?? layer.seed.addressee ?? {}) as Record<string, unknown>;
    const who = [addressee.recipient_position, addressee.recipient_name].filter(Boolean).join(" ");
    if (who) return `${label}: ${who}`;
  }
  return number ? `${label} № ${number}` : label;
}

export function DayTab({ project, onDirty, canRemember = false }: {
  project: MassBlastProjectV2;
  canRemember?: boolean;
  /** Есть ли несохранённые правки хоть в одном слое. */
  onDirty?: (dirty: boolean) => void;
}) {
  const dirtyLayers = useRef(new Set<string>());
  const markDirty = useCallback((layerId: string, dirty: boolean) => {
    const before = dirtyLayers.current.size > 0;
    if (dirty) dirtyLayers.current.add(layerId);
    else dirtyLayers.current.delete(layerId);
    const after = dirtyLayers.current.size > 0;
    if (before !== after) onDirty?.(after);
  }, [onDirty]);
  const [layers, setLayers] = useState<MassBlastLayer[]>([]);
  const [available, setAvailable] = useState<LayerAvailability[]>([]);
  const [addressees, setAddressees] = useState<NotificationAddressees | null>(null);
  const [addressee, setAddressee] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");

  const reload = useCallback(async () => {
    const [items, kinds] = await Promise.all([api.massBlast.layers(project.id), api.massBlast.layersAvailable(project.id)]);
    setLayers(items);
    setAvailable(kinds);
    if (kinds.some((item) => item.kind === "NOTIFICATION" && (item.can_open || item.count > 0))) {
      setAddressees(await api.massBlast.addressees(project.id).catch(() => null));
    }
  }, [project.id]);

  useEffect(() => {
    setMessage("");
    void reload().catch((reason) => setMessage(errorText(reason, "Не удалось прочитать слои проекта.")));
  }, [reload, project.lifecycle_status, project.current_revision_id]);

  async function open(kind: LayerKind, payload: Record<string, unknown> = {}) {
    setBusy(true);
    setMessage("");
    try {
      await api.massBlast.createLayer(project.id, { kind, payload });
      await reload();
    } catch (reason) {
      setMessage(errorText(reason, "Не удалось открыть слой."));
    } finally {
      setBusy(false);
    }
  }

  async function notifyAll() {
    setBusy(true);
    setMessage("");
    try {
      for (const item of addressees?.items ?? []) {
        if (!item.taken) await api.massBlast.createLayer(project.id, { kind: "NOTIFICATION", payload: { notification_code: item.code } });
      }
      await reload();
    } catch (reason) {
      setMessage(errorText(reason, "Не удалось создать уведомления."));
      await reload().catch(() => undefined);
    } finally {
      setBusy(false);
    }
  }

  function replace(next: MassBlastLayer) {
    setLayers((current) => current.map((item) => (item.id === next.id ? next : item)));
    void api.massBlast.layersAvailable(project.id).then(setAvailable).catch(() => undefined);
  }

  return (
    <>
      {ORDER.map((kind) => {
        const info = available.find((item) => item.kind === kind);
        const own = layers.filter((layer) => layer.kind === kind);
        const label = info?.label ?? kind;
        const free = (addressees?.items ?? []).filter((item) => !item.taken);
        return (
          <section key={kind} className="mb-layer-group" aria-label={label}>
            {own.map((layer, index) => (
              <LayerCard key={layer.id} layer={layer} projectStatus={project.lifecycle_status} onChange={replace} onIssued={reload} onDirty={markDirty} canRemember={canRemember}
                label={cardLabel(layer, label, own.length > 1 ? index + 1 : 0)} />
            ))}
            {info && !info.can_open && own.length === 0 && (
              <fieldset className="mb-layer">
                <legend>{label}</legend>
                <small className="drill-hint">{info.reason}</small>
              </fieldset>
            )}
            {info?.can_open && kind === "NOTIFICATION" && addressees?.registry && (
              <fieldset className="mb-layer">
                <legend>{own.length ? "Ещё уведомление" : label}</legend>
                {free.length ? (
                  <div className="drill-downloads">
                    <label>
                      Адресат из справочника карьера
                      <select value={addressee} onChange={(event) => setAddressee(event.target.value)} disabled={busy}>
                        <option value="">— выберите —</option>
                        {free.map((item) => <option key={item.code} value={item.code}>{item.label}</option>)}
                      </select>
                    </label>
                    <button type="button" className="secondary-button" disabled={busy || !addressee}
                      onClick={() => void open("NOTIFICATION", { notification_code: addressee }).then(() => setAddressee(""))}>
                      Создать уведомление
                    </button>
                    {free.length > 1 && (
                      <button type="button" className="secondary-button" disabled={busy} onClick={() => void notifyAll()}>
                        Уведомления всем адресатам
                      </button>
                    )}
                  </div>
                ) : (
                  <small className="drill-hint">Уведомления всем адресатам справочника уже созданы.</small>
                )}
              </fieldset>
            )}
            {info?.can_open && !(kind === "NOTIFICATION" && addressees?.registry) && (own.length === 0 || info.multiple) && (
              <div className="plans-actions">
                <button type="button" className={own.length ? "secondary-button" : "calculate-button"} disabled={busy} onClick={() => void open(kind)}>
                  {own.length === 0 ? `Открыть «${label}»` : kind === "NARYAD" ? "Ещё наряд-путёвка" : `Ещё «${label}»`}
                </button>
              </div>
            )}
          </section>
        );
      })}
      {message && <small className="form-error">{message}</small>}
    </>
  );
}
