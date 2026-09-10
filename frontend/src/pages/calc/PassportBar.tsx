import { useEffect, useMemo, useRef, useState } from "react";
import { api } from "../../api/endpoints";
import { revisionsToFetch, siteNameFor, type SiteNamesByRevision } from "./passportSiteNames";
import type { BlastGeometryResponse } from "../../types";
import type { TechnicalPassport } from "../../types/blockEconomics";

/**
 * Технические паспорта блока: вход во вкладку «Экономика».
 *
 * Паспорт фиксирует рассчитанный блок и ревизию справочников, поэтому
 * экономика считается по нему, а не по текущему состоянию формы.
 *
 * Объект работ здесь не выбирается: паспорт принадлежит тому объекту, что
 * выбран в шапке страницы (`objectName`) — по нему считался сам блок, и
 * второй выбор мог с ним разойтись. По нему же отфильтрован список
 * сохранённых паспортов.
 */
export type PassportVariant = { key: string; label: string; geometry: BlastGeometryResponse | null };

export function PassportBar({
  variants,
  objectName,
  onOpenEconomics,
}: {
  /** Панели расчёта с их блоками: в паспорт уходит выбранная пользователем. */
  variants: PassportVariant[];
  /** Активный объект работ страницы: и адрес нового паспорта, и фильтр списка. */
  objectName: string;
  onOpenEconomics?: (passportId: string) => void;
}) {
  const [passports, setPassports] = useState<TechnicalPassport[]>([]);
  const [sites, setSites] = useState<{ code: string; name: string }[]>([]);
  const [currentRevisionId, setCurrentRevisionId] = useState("");
  // Имена объектов по ревизии справочников, на которой выпущен паспорт: объект
  // могли переименовать (или удалить) позже — список не должен показать новое
  // имя у старой записи. Так же считает вкладка «Экономика» для того же паспорта.
  const [namesByRevision, setNamesByRevision] = useState<SiteNamesByRevision>({});
  // Зеркало namesByRevision для эффекта ниже: он не должен зависеть от
  // namesByRevision (иначе каждый пришедший снимок его перезапускает и
  // дублирует запросы для ещё не ответивших ревизий), но обязан видеть
  // актуальные данные, а не устаревшее замыкание.
  const namesByRevisionRef = useRef<SiteNamesByRevision>(namesByRevision);
  // Ревизии, запрос которых уже отправлен и ещё не завершился.
  const pendingRevisionsRef = useRef<Set<string>>(new Set());
  const [passportName, setPassportName] = useState("");
  const [variantKey, setVariantKey] = useState(variants[0]?.key ?? "");
  const [busy, setBusy] = useState(false);
  // Паспорт, который сейчас удаляется: блокируем его кнопку, не весь список.
  const [deletingId, setDeletingId] = useState("");
  const [error, setError] = useState("");
  const variant = variants.find((item) => item.key === variantKey) ?? variants[0];
  const geometry = variant?.geometry ?? null;
  const currentNames = useMemo(
    () => Object.fromEntries(sites.map((site) => [site.code, site.name])),
    [sites],
  );
  // Объект работ из шапки — в справочнике он же «карьер/объект» с кодом.
  // Пока справочник не загружен, кода нет: сохранять и грузить список нечего.
  const siteCode = useMemo(
    () => sites.find((site) => site.name === objectName)?.code ?? "",
    [sites, objectName],
  );
  const siteMissing = sites.length > 0 && !siteCode;

  useEffect(() => {
    api.economics
      .referenceSnapshot()
      .then((snapshot) => {
        setSites(
          // Только действующие объекты: список в шапке страницы собран из них
          // же (`active_items("sites")` в legacy_adapter). Иначе закрытый
          // объект с тем же названием мог перехватить имя у действующего, и
          // паспорт ушёл бы на закрытый код.
          (snapshot.sections.sites ?? [])
            .filter((item) => item.is_active)
            .map((item) => ({ code: item.code, name: item.name })),
        );
        setCurrentRevisionId(snapshot.revision_id);
      })
      .catch((reason) =>
        setError(reason instanceof Error ? reason.message : "Не удалось загрузить справочник объектов."),
      );
  }, []);

  // Список — только паспорта объекта из шапки: чужие объекты сюда не
  // попадают, поэтому при переключении объекта список перезапрашивается.
  useEffect(() => {
    if (!siteCode) {
      setPassports([]);
      return;
    }
    let cancelled = false;
    api.economics
      .technicalPassports(siteCode)
      .then((saved) => {
        if (cancelled) return;
        setPassports(saved);
        // Список этого объекта получен — прошлая ошибка (другого объекта или
        // неудачной попытки) больше ни о чём не говорит.
        setError("");
      })
      .catch((reason) => {
        if (!cancelled) {
          setError(reason instanceof Error ? reason.message : "Не удалось загрузить паспорта.");
        }
      });
    return () => {
      cancelled = true;
    };
  }, [siteCode]);

  // Для видимых паспортов (первые 8) подгружаем снимок каждой их ревизии —
  // кроме текущей, она уже загружена выше. Ошибка одной ревизии не должна
  // ломать список: паспорт просто откатится к текущему имени или коду, а
  // сама ревизия запоминается как «недоступна» и не запрашивается повторно.
  // Эффект намеренно не зависит от namesByRevision: иначе каждый пришедший
  // снимок перезапускал бы его и дублировал запросы для ревизий, чьи ответы
  // ещё не пришли (pendingRevisionsRef защищает от этого же в рамках одного
  // прохода эффекта).
  useEffect(() => {
    const revisionIds = revisionsToFetch(
      passports.slice(0, 8),
      namesByRevisionRef.current,
      pendingRevisionsRef.current,
      currentRevisionId,
    );
    if (revisionIds.length === 0) return;
    revisionIds.forEach((revisionId) => {
      pendingRevisionsRef.current.add(revisionId);
      api.economics
        .referenceSnapshot(revisionId)
        .then((snapshot) => {
          const names: Record<string, string> = {};
          for (const item of snapshot.sections.sites ?? []) names[item.code] = item.name;
          namesByRevisionRef.current = { ...namesByRevisionRef.current, [revisionId]: names };
          setNamesByRevision(namesByRevisionRef.current);
        })
        .catch(() => {
          namesByRevisionRef.current = { ...namesByRevisionRef.current, [revisionId]: {} };
          setNamesByRevision(namesByRevisionRef.current);
        })
        .finally(() => {
          pendingRevisionsRef.current.delete(revisionId);
        });
    });
  }, [passports, currentRevisionId]);

  async function savePassport() {
    if (!geometry || !siteCode) return;
    setBusy(true);
    setError("");
    try {
      const created = await api.economics.createTechnicalPassport({
        site_code: siteCode,
        object_name: passportName.trim() || `Блок ${Math.round(geometry.block.block_volume_m3)} м³`,
        block: geometry.block as unknown as Record<string, unknown>,
        selected_variant: { label: geometry.label },
      });
      setPassports((rows) => [created, ...rows]);
      setPassportName("");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Не удалось сохранить паспорт.");
    } finally {
      setBusy(false);
    }
  }

  /** Удаление паспорта: строка остаётся на сервере (её держат сохранённые
   * прогоны экономики), но из списка уходит и новых расчётов не принимает. */
  async function removePassport(passport: TechnicalPassport) {
    const confirmed = window.confirm(
      `Удалить паспорт «${passport.object_name}»? ` +
        "Сохранённые расчёты экономики по нему останутся.",
    );
    if (!confirmed) return;
    setDeletingId(passport.id);
    setError("");
    try {
      await api.economics.deleteTechnicalPassport(passport.id);
      setPassports((rows) => rows.filter((row) => row.id !== passport.id));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Не удалось удалить паспорт.");
    } finally {
      setDeletingId("");
    }
  }

  return (
    <section className="panel passport-bar">
      <header><b>Технические паспорта</b><span>{objectName || "Экономика блока"}</span></header>
      <div className="panel-body">
        {error && <div className="page-error" role="alert">{error}</div>}
        {siteMissing && (
          <div className="page-error" role="alert">
            Объекта «{objectName}» нет в справочнике «Карьеры и объекты» — паспорт сохранить не по
            чему. Выберите другой объект в шапке или заведите этот в справочниках.
          </div>
        )}
        <div className="economic-fields-grid">
          <label>
            Название паспорта
            <input
              value={passportName}
              placeholder="Блок, м³"
              onChange={(event) => setPassportName(event.target.value)}
            />
          </label>
          <label>
            Вариант расчёта
            <select value={variant?.key ?? ""} onChange={(event) => setVariantKey(event.target.value)}>
              {variants.map((item) => (
                <option key={item.key} value={item.key} disabled={!item.geometry}>
                  {item.label}{item.geometry ? "" : " (нет расчёта)"}
                </option>
              ))}
            </select>
          </label>
          <div className="button-row">
            <button type="button" onClick={() => void savePassport()} disabled={busy || !geometry || !siteCode}>
              Сохранить паспорт
            </button>
          </div>
        </div>
        {geometry && variant && (
          // В паспорт уходит блок выбранной панели с её зарядом и недозарядом —
          // показываем это до сохранения, чтобы масса не была сюрпризом.
          <p className="page-caption">
            В паспорт пойдёт «{variant.label}» по объекту «{objectName}»:{" "}
            {Math.round(geometry.block.total_charge_mass_kg).toLocaleString("ru-RU")} кг ВВ,{" "}
            {geometry.block.total_holes} скважин, {Math.round(geometry.block.drilling_footage_m).toLocaleString("ru-RU")} п.м.,{" "}
            {geometry.block.specific_q_kg_m3.toFixed(2)} кг/м³ с доп. скважинами. Кнопка «Экономика» открывает сохранённый
            паспорт: чтобы передать текущий расчёт, сначала сохраните новый.
          </p>
        )}
        {passports.length === 0 ? (
          <p className="page-caption">Сохранённых паспортов по этому объекту нет.</p>
        ) : (
          <div className="passport-list">
            {passports.slice(0, 8).map((passport) => (
              <div className="passport-list-row" key={passport.id}>
                <span>
                  <b>{passport.object_name}</b>
                  <small>
                    {siteNameFor(passport, namesByRevision, currentNames)} · вер.{" "}
                    {passport.version_no} · {new Date(passport.created_at).toLocaleDateString("ru-RU")} ·{" "}
                    {Math.round(Number(passport.physical.explosive_kg ?? 0)).toLocaleString("ru-RU")} кг ВВ
                  </small>
                </span>
                <em>{Number(passport.physical.rock_volume_m3 ?? 0).toLocaleString("ru-RU")} м³</em>
                <button
                  type="button"
                  className="secondary-button"
                  onClick={() => onOpenEconomics?.(passport.id)}
                  disabled={!onOpenEconomics}
                >
                  Экономика
                </button>
                <button
                  type="button"
                  className="danger-button"
                  onClick={() => void removePassport(passport)}
                  disabled={deletingId === passport.id}
                  title="Удалить паспорт из списка"
                >
                  {deletingId === passport.id ? "Удаление…" : "Удалить"}
                </button>
              </div>
            ))}
          </div>
        )}
      </div>
    </section>
  );
}
