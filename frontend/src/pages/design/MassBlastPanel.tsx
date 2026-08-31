import { useEffect, useMemo, useState } from "react";
import { api } from "../../api/endpoints";
import type { MassBlastAttachment, MassBlastDocument, MassBlastProject, MassBlastProjectInput, MassBlastValidation } from "../../types/design";

const today = () => new Date().toISOString().slice(0, 10);

export function MassBlastPanel({ designId, designName }: { designId: string; designName: string }) {
  const [project, setProject] = useState<MassBlastProject | null>(null);
  const [documents, setDocuments] = useState<MassBlastDocument[]>([]);
  const [attachments, setAttachments] = useState<MassBlastAttachment[]>([]);
  const [attachmentKind, setAttachmentKind] = useState("PLAN");
  const [validation, setValidation] = useState<MassBlastValidation | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [siteCode, setSiteCode] = useState("");
  const [objectName, setObjectName] = useState(designName || "");
  const [projectName, setProjectName] = useState(`Массовый взрыв — ${designName || "новый проект"}`);
  const [blastDate, setBlastDate] = useState(today());
  const [blastTime, setBlastTime] = useState("");
  const [dangerZone, setDangerZone] = useState("0");
  const [signalProfile, setSignalProfile] = useState("THREE_SIGNALS");
  const [blastManager, setBlastManager] = useState("");
  const [explosivesSupervisor, setExplosivesSupervisor] = useState("");
  const [guardLocation, setGuardLocation] = useState("");
  const [additionalDesignIds, setAdditionalDesignIds] = useState("");

  const payload = useMemo<MassBlastProjectInput>(() => ({
    name: projectName.trim(),
    site_code: siteCode.trim(),
    object_name: objectName.trim(),
    customer_code: "",
    blast_date: blastDate,
    blast_time: blastTime.trim(),
    document_profile_code: "STANDARD",
    blocks: Array.from(new Set([designId, ...additionalDesignIds.split(/[\s,;]+/).map((item) => item.trim()).filter(Boolean)])).filter(Boolean)
      .map((id, index) => ({ design_id: id, code: id === designId ? (designName || "Блок") : `Блок ${index + 1}`, horizon: "" })),
    responsibilities: [
      { role_code: "blast_manager", employee_code: blastManager.trim(), employee_name: blastManager.trim(), position_name: "Руководитель взрывных работ" },
      { role_code: "explosives_supervisor", employee_code: explosivesSupervisor.trim(), employee_name: explosivesSupervisor.trim(), position_name: "Ответственный за ВМ" },
    ].filter((item) => item.employee_code),
    safety_plan: { danger_zone_radius_m: Number(dangerZone) || 0 },
    charging_schedule: [],
    signal_plan: { profile_code: signalProfile.trim() },
    guard_posts: guardLocation.trim() ? [{ code: "POST-1", location: guardLocation.trim(), responsible_employee_code: "", notes: "" }] : [],
    notifications: [],
  }), [additionalDesignIds, blastDate, blastManager, blastTime, dangerZone, designId, designName, explosivesSupervisor, guardLocation, objectName, projectName, signalProfile, siteCode]);

  async function refreshDocuments(id: string) {
    setDocuments(await api.massBlast.documents(id));
  }
  async function refreshAttachments(id: string) {
    setAttachments(await api.massBlast.attachments(id));
  }

  useEffect(() => {
    let active = true;
    api.massBlast.list().then((items) => {
      const candidate = items.find((item) => item.block_design_ids.includes(designId));
      if (!active || !candidate) return;
      return api.massBlast.get(candidate.id).then((full) => {
        if (!active) return;
        setProject(full);
        setSiteCode(full.site_code);
        setObjectName(full.object_name);
        setProjectName(full.name);
        setBlastDate(full.blast_date);
        setBlastTime(full.blast_time);
        setDangerZone(String(full.safety_plan?.danger_zone_radius_m ?? 0));
        setSignalProfile(String(full.signal_plan?.profile_code ?? "THREE_SIGNALS"));
        setBlastManager(full.responsibilities.find((item) => item.role_code === "blast_manager")?.employee_name || "");
        setExplosivesSupervisor(full.responsibilities.find((item) => item.role_code === "explosives_supervisor")?.employee_name || "");
        setGuardLocation(full.guard_posts[0]?.location || "");
        setAdditionalDesignIds((full.blocks || []).map((block) => String(block.design_id || "")).filter((id) => id && id !== designId).join(", "));
        void refreshDocuments(full.id).catch(() => undefined);
        void refreshAttachments(full.id).catch(() => undefined);
      });
    }).catch(() => undefined);
    return () => { active = false; };
  }, [designId]);

  async function saveDraft() {
    if (!designId) {
      setMessage("Сначала сохраните технический паспорт БВР, чтобы зафиксировать источник блока.");
      return;
    }
    setBusy(true); setMessage("");
    try {
      const saved = project
        ? await api.massBlast.save(project.id, { ...payload, expected_version: project.version })
        : await api.massBlast.create(payload);
      setProject(saved);
      setValidation(null);
      setMessage("Черновик проекта массового взрыва сохранён в project1.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Не удалось сохранить черновик.");
    } finally { setBusy(false); }
  }

  async function runValidation() {
    if (!project) { setMessage("Сначала сохраните черновик."); return; }
    setBusy(true); setMessage("");
    try { setValidation(await api.massBlast.validate(project.id, true)); }
    catch (error) { setMessage(error instanceof Error ? error.message : "Не удалось проверить проект."); }
    finally { setBusy(false); }
  }

  async function releaseRevision() {
    if (!project) { setMessage("Сначала сохраните черновик."); return; }
    setBusy(true); setMessage("");
    try {
      const revision = await api.massBlast.createRevision(project.id, { expected_version: project.version, require_attachments: true });
      const updated = await api.massBlast.get(project.id);
      setProject(updated);
      setMessage(`Ревизия №${revision.revision_no} создана. Теперь её можно согласовать и выпустить.`);
    } catch (error) { setMessage(error instanceof Error ? error.message : "Не удалось выпустить ревизию."); }
    finally { setBusy(false); }
  }

  async function generate(format: "PDF" | "XLSX" | "ZIP") {
    if (!project?.current_revision_id) { setMessage("Сначала создайте ревизию проекта."); return; }
    setBusy(true); setMessage("");
    try {
      const document = await api.massBlast.generateDocument(project.id, {
        revision_id: project.current_revision_id, kind: format === "ZIP" ? "PACKAGE" : "PROJECT", format,
      });
      await refreshDocuments(project.id);
      setMessage(`Сформирован файл «${document.filename}».`);
    } catch (error) { setMessage(error instanceof Error ? error.message : "Не удалось сформировать документ."); }
    finally { setBusy(false); }
  }

  async function approve(roleCode: string) {
    if (!project?.current_revision_id) return;
    setBusy(true); setMessage("");
    try {
      await api.massBlast.approveRevision(project.current_revision_id, { role_code: roleCode, decision: "approved" });
      setMessage(`Согласование по роли «${roleCode}» записано для текущей контрольной суммы.`);
    } catch (error) { setMessage(error instanceof Error ? error.message : "Не удалось записать согласование."); }
    finally { setBusy(false); }
  }

  async function approveProject() {
    if (!project) return;
    setBusy(true); setMessage("");
    try {
      const updated = await api.massBlast.transition(project.id, { to_status: "approved", expected_version: project.version, confirm: true });
      setProject(updated);
      setMessage("Проект утверждён после обязательных согласований.");
    } catch (error) { setMessage(error instanceof Error ? error.message : "Не удалось утвердить проект."); }
    finally { setBusy(false); }
  }

  async function returnToDraft() {
    if (!project) return;
    setBusy(true); setMessage("");
    try {
      const updated = await api.massBlast.transition(project.id, { to_status: "draft", expected_version: project.version, confirm: true, note: "Доработка проекта" });
      setProject(updated);
      setMessage("Проект возвращён в черновик. Изменение создаст следующую ревизию.");
    } catch (error) { setMessage(error instanceof Error ? error.message : "Не удалось вернуть проект в черновик."); }
    finally { setBusy(false); }
  }

  async function uploadAttachment(file: File | undefined) {
    if (!file || !project) return;
    setBusy(true); setMessage("");
    try {
      await api.massBlast.uploadAttachment(project.id, attachmentKind, file);
      await refreshAttachments(project.id);
      setMessage(`Приложение «${file.name}» загружено.`);
    } catch (error) { setMessage(error instanceof Error ? error.message : "Не удалось загрузить приложение."); }
    finally { setBusy(false); }
  }

  async function removeAttachment(attachmentId: string) {
    if (!project) return;
    setBusy(true); setMessage("");
    try {
      await api.massBlast.deleteAttachment(project.id, attachmentId);
      await refreshAttachments(project.id);
    } catch (error) { setMessage(error instanceof Error ? error.message : "Не удалось удалить приложение."); }
    finally { setBusy(false); }
  }

  return (
    <section className="panel">
      <header><b>Проект массового взрыва</b><span>контур документации</span></header>
      <div className="panel-body">
        <small>
          Технические параметры берутся из текущего паспорта БВР и фиксируются в ревизии. Себестоимость и рыночная цена в официальный комплект не попадают.
        </small>
        <div className="form-grid compact-form" style={{ marginTop: 12 }}>
          <label>Объект, код<input value={siteCode} onChange={(event) => setSiteCode(event.target.value)} placeholder="SITE-001" disabled={busy || project?.lifecycle_status !== "draft" && !!project} /></label>
          <label>Наименование объекта<input value={objectName} onChange={(event) => setObjectName(event.target.value)} disabled={busy || project?.lifecycle_status !== "draft" && !!project} /></label>
          <label>Наименование проекта<input value={projectName} onChange={(event) => setProjectName(event.target.value)} disabled={busy || project?.lifecycle_status !== "draft" && !!project} /></label>
          <label>Дата взрыва<input type="date" value={blastDate} onChange={(event) => setBlastDate(event.target.value)} disabled={busy || project?.lifecycle_status !== "draft" && !!project} /></label>
          <label>Время<input type="time" value={blastTime} onChange={(event) => setBlastTime(event.target.value)} disabled={busy || project?.lifecycle_status !== "draft" && !!project} /></label>
          <label>Опасная зона, м<input type="number" min="0" value={dangerZone} onChange={(event) => setDangerZone(event.target.value)} disabled={busy || project?.lifecycle_status !== "draft" && !!project} /></label>
          <label>Профиль сигналов<input value={signalProfile} onChange={(event) => setSignalProfile(event.target.value)} disabled={busy || project?.lifecycle_status !== "draft" && !!project} /></label>
          <label>Руководитель ВР<input value={blastManager} onChange={(event) => setBlastManager(event.target.value)} disabled={busy || project?.lifecycle_status !== "draft" && !!project} /></label>
          <label>Ответственный за ВМ<input value={explosivesSupervisor} onChange={(event) => setExplosivesSupervisor(event.target.value)} disabled={busy || project?.lifecycle_status !== "draft" && !!project} /></label>
          <label>Пост охраны<input value={guardLocation} onChange={(event) => setGuardLocation(event.target.value)} disabled={busy || project?.lifecycle_status !== "draft" && !!project} /></label>
          <label>Дополнительные паспорта БВР (ID через запятую)<input value={additionalDesignIds} onChange={(event) => setAdditionalDesignIds(event.target.value)} placeholder="design-a, design-b" disabled={busy || project?.lifecycle_status !== "draft" && !!project} /></label>
        </div>
        <small>Источник блока: {designId ? `${designName || designId} (${designId})` : "сначала сохраните паспорт"}.</small>
        <div className="plans-actions">
          <button className="secondary-button" onClick={saveDraft} disabled={busy || (!!project && project.lifecycle_status !== "draft")}>Сохранить черновик</button>
          <button className="secondary-button" onClick={runValidation} disabled={busy || !project}>Проверить</button>
          <button className="calculate-button" onClick={releaseRevision} disabled={busy || !project || project.lifecycle_status !== "draft"}>Создать ревизию</button>
        </div>
        {project?.lifecycle_status === "draft" && <div className="form-grid compact-form" style={{ marginTop: 10 }}>
          <label>Вид приложения
            <select value={attachmentKind} onChange={(event) => setAttachmentKind(event.target.value)} disabled={busy}>
              <option value="PLAN">План скважин</option>
              <option value="CHARGING_SCHEME">Схема заряжания</option>
              <option value="DANGER_ZONE">Опасная зона</option>
              <option value="GUARD_POSTS">Посты охраны</option>
              <option value="SHOTPLUS_XLSX">Выгрузка SHOTPlus XLSX</option>
              <option value="OTHER">Другое</option>
            </select>
          </label>
          <label>Графическое приложение / выгрузка
            <input type="file" accept=".pdf,.xlsx,.dxf,.dwg,.png,.jpg,.jpeg" onChange={(event) => void uploadAttachment(event.target.files?.[0])} disabled={busy} />
          </label>
        </div>}
        {project?.current_revision_id && <div className="plans-actions">
          {project.lifecycle_status === "in_review" && <>
            <button className="secondary-button" onClick={() => approve("blast_manager")} disabled={busy}>Согласовать: руководитель ВР</button>
            <button className="secondary-button" onClick={() => approve("explosives_supervisor")} disabled={busy}>Согласовать: ответственный за ВМ</button>
            <button className="calculate-button" onClick={approveProject} disabled={busy}>Утвердить проект</button>
            <button className="secondary-button" onClick={returnToDraft} disabled={busy}>Вернуть в черновик</button>
          </>}
          {project.lifecycle_status !== "draft" && project.lifecycle_status !== "in_review" && <>
            <button className="secondary-button" onClick={() => generate("PDF")} disabled={busy}>PDF проекта</button>
            <button className="secondary-button" onClick={() => generate("XLSX")} disabled={busy}>XLSX ведомость</button>
            <button className="calculate-button" onClick={() => generate("ZIP")} disabled={busy}>Скачать комплект</button>
          </>}
        </div>}
        {project && <small>Статус: {project.lifecycle_status} · версия черновика: {project.version}{project.current_revision_id ? " · ревизия выпущена" : ""}.</small>}
        {message && <small className="frag-warnings">{message}</small>}
        {validation && <div className="validation-list">
          <b>{validation.valid ? "Проверка пройдена" : "Требуется исправление"}</b>
          {validation.issues.map((issue) => <small key={`${issue.level}:${issue.code}:${issue.path}`} className={issue.level === "error" ? "form-error" : "frag-warnings"}>{issue.level === "error" ? "Ошибка" : "Предупреждение"}: {issue.message}</small>)}
        </div>}
        {attachments.length > 0 && <div className="validation-list"><b>Приложения</b>
          {attachments.map((item) => <div key={item.id}>
            <a href={project ? api.massBlast.attachmentUrl(project.id, item.id) : undefined}>{item.kind}: {item.filename}</a>
            {item.revision_id ? <small> · выпущено в ревизии</small> : project?.lifecycle_status === "draft" && <button className="link-button" onClick={() => void removeAttachment(item.id)} disabled={busy}>Удалить</button>}
          </div>)}
        </div>}
        {documents.length > 0 && <div className="validation-list"><b>Сформированные документы</b>
          {documents.map((item) => <a key={item.id} href={api.massBlast.documentUrl(item.id)}>{item.format}: {item.filename}</a>)}
        </div>}
      </div>
    </section>
  );
}
