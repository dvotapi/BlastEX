// Панель «Проект МВ» в этапе «Отчёт» «Проектирования» (TASK-018, PR 6).
// При включённом модуле `mass_blast_v2` — проект по форме ВМ.09.03: коротко
// статус и кнопки, форма — в окне `MassBlastDialog`. Проект по прежней форме
// (контекст v1) и выключенный модуль — прежняя панель без изменений; черновик
// v1 можно перевести на форму ВМ.09.03 (только вперёд).
import { useEffect, useRef, useState } from "react";
import { api } from "../../api/endpoints";
import { useFeatures } from "../../app/useFeatures";
import { ruDate } from "../../lib/format";
import type { MassBlastProjectInputV2, MassBlastProjectV2 } from "../../types/massBlast";
import { snapshotStale } from "./designParams";
import { CreateProjectDialog } from "./massBlast/CreateProjectDialog";
import { LegacyMassBlastPanel } from "./massBlast/LegacyPanel";
import { MassBlastDialog } from "./massBlast/MassBlastDialog";
import { STATUS_LABELS } from "./massBlast/ProjectDocuments";
import { download, errorText } from "./massBlast/ui";

type Found = { project: MassBlastProjectV2 | null; legacy: boolean };

/** Перевод черновика v1 на форму ВМ.09.03: payload проекта + `context_version: 2`. */
function convertInput(project: MassBlastProjectV2): MassBlastProjectInputV2 {
  return {
    name: project.name,
    site_code: project.site_code,
    object_name: project.object_name,
    customer_code: project.customer_code ?? "",
    blast_date: project.blast_date,
    blast_time: project.blast_time ?? "",
    document_profile_code: project.document_profile_code || "STANDARD",
    reference_revision_id: project.reference_revision_id ?? null,
    blocks: (project.blocks ?? []).map((block) => ({
      design_id: String(block.design_id ?? ""),
      technical_passport_id: (block.technical_passport_id as string | null | undefined) ?? null,
      code: String(block.code ?? ""),
      horizon: String(block.horizon ?? ""),
    })),
    responsibilities: project.responsibilities ?? [],
    safety_plan: project.safety_plan ?? {},
    charging_schedule: project.charging_schedule ?? [],
    signal_plan: project.signal_plan ?? {},
    guard_posts: project.guard_posts ?? [],
    notifications: project.notifications ?? [],
    context_version: 2,
    expected_version: project.version,
  } as unknown as MassBlastProjectInputV2;
}

export function MassBlastPanel({
  designId,
  designName,
  designSha256 = "",
  designedDirty = false,
}: {
  designId: string;
  designName: string;
  /** `designed_sha256` сохранённого проекта блока (TASK-017, PR 3). */
  designSha256?: string;
  /** Проектная часть изменена и не сохранена (сдвиг, правка сети). */
  designedDirty?: boolean;
}) {
  const { mass_blast_v2: enabled, loaded } = useFeatures();
  const [found, setFound] = useState<Found | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [open, setOpen] = useState(false);
  const [creating, setCreating] = useState(false);
  const [reload, setReload] = useState(0);
  const shownFor = useRef(designId);

  useEffect(() => {
    if (!enabled) return;
    if (shownFor.current !== designId) {
      shownFor.current = designId;
      setOpen(false);
      setCreating(false);
    }
    setFound(null);
    setError("");
    if (!designId) return;
    let alive = true;
    api.massBlast
      .list()
      .then(async (items) => {
        const candidate = items.find((item) => item.block_design_ids.includes(designId));
        if (!candidate) return { project: null, legacy: false };
        const project = await api.massBlast.getV2(candidate.id);
        return { project, legacy: Number(project.context_version ?? 1) < 2 };
      })
      .then((value) => alive && setFound(value))
      .catch((reason) => alive && setError(errorText(reason, "Не удалось прочитать проект массового взрыва.")));
    return () => {
      alive = false;
    };
  }, [designId, enabled, reload]);

  // Пока состав модулей не прочитан — ничего: иначе на миг мелькнула бы прежняя панель v1.
  if (!loaded) return null;
  if (!enabled) return <LegacyMassBlastPanel designId={designId} designName={designName} />;

  if (found?.legacy && found.project) {
    const draft = found.project.lifecycle_status === "draft";
    return (
      <>
        {draft && (
          <section className="panel">
            <header><b>Форма ВМ.09.03</b><span>проект создан по прежней форме</span></header>
            <div className="panel-body">
              <small>Черновик можно перевести на форму ВМ.09.03: расчёт зон, техрасчёт, распорядок, графика и слои дня взрыва. Обратно перевести нельзя.</small>
              <div className="plans-actions">
                <button type="button" className="calculate-button" disabled={busy} onClick={() => {
                  if (!window.confirm("Перевести черновик на форму ВМ.09.03? Обратно на прежнюю форму перевести нельзя.")) return;
                  setBusy(true);
                  setError("");
                  // Черновик могли сохранить в прежней панели: версия — свежая, с сервера.
                  api.massBlast
                    .getV2(found.project!.id)
                    .then((fresh) => api.massBlast.saveV2(fresh.id, convertInput(fresh)))
                    .then(() => setReload((value) => value + 1))
                    .catch((reason) => setError(errorText(reason, "Не удалось перевести проект.")))
                    .finally(() => setBusy(false));
                }}>
                  Перевести на форму ВМ.09.03
                </button>
              </div>
              {error && <small className="form-error">{error}</small>}
            </div>
          </section>
        )}
        <LegacyMassBlastPanel designId={designId} designName={designName} />
      </>
    );
  }

  const project = found?.project ?? null;
  const approved = project ? ["approved", "executed", "closed"].includes(project.lifecycle_status) : false;
  const block = project?.blocks.find((item) => item.design_id === designId);
  const stale = Boolean(block) && snapshotStale(block?.design_sha256, designSha256, designedDirty);
  return (
    <section className="panel">
      <header><b>Проект массового взрыва</b><span>ВМ.09.03</span></header>
      <div className="panel-body">
        {!designId && <small>Сначала сохраните проект блока: проект МВ строится по сохранённому проекту блока.</small>}
        {designId && !found && !error && <small>Ищем проект массового взрыва блока…</small>}
        {designId && found && !project && (
          <div className="plans-actions">
            <button type="button" className="calculate-button" onClick={() => setCreating(true)}>Создать проект МВ</button>
          </div>
        )}
        {project && (
          <>
            <small>
              {project.requisites?.project_no ? `№ ${project.requisites.project_no} · ` : ""}
              взрыв {ruDate(project.blast_date)}{project.blast_time ? ` в ${project.blast_time}` : ""} · {STATUS_LABELS[project.lifecycle_status]}
              {project.current_revision_id ? " · ревизия выпущена" : ""}
            </small>
            {stale && (
              <small className="frag-warnings">Устарел: проект блока изменён после добавления в проект МВ — обновите снимок блока и выпустите новую ревизию.</small>
            )}
            <div className="plans-actions">
              <button type="button" className="secondary-button" onClick={() => setOpen(true)}>Открыть проект</button>
              {approved && project.current_revision_id && (
                <button type="button" className="calculate-button" disabled={busy} onClick={() => {
                  setBusy(true);
                  setError("");
                  download(api.massBlast.packageUrl(project.current_revision_id!), "package.zip")
                    .catch((reason) => setError(errorText(reason, "Не удалось скачать комплект.")))
                    .finally(() => setBusy(false));
                }}>
                  Весь комплект
                </button>
              )}
            </div>
          </>
        )}
        {error && <small className="form-error">{error}</small>}
      </div>
      {creating && (
        <CreateProjectDialog designId={designId} designName={designName} onClose={() => setCreating(false)}
          onCreated={(created) => {
            setCreating(false);
            setFound({ project: created, legacy: false });
            setOpen(true);
          }} />
      )}
      {open && project && (
        <MassBlastDialog project={project} onClose={() => { setOpen(false); setReload((value) => value + 1); }}
          onChange={(next) => setFound((current) => (current?.project?.id === next.id ? { ...current, project: next } : current))} />
      )}
    </section>
  );
}
