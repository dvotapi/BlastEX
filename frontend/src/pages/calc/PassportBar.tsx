import { useEffect, useMemo, useRef, useState } from "react";
import { api } from "../../api/endpoints";
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
 * сохранённых паспортов. Сохранённые паспорта — выпадающий список, а
 * «Экономика» и «Удалить» действуют на выбранный в нём: панель должна
 * уместиться в верхний ряд листа рядом с исходными данными и вариантами.
 */
/** `pending` — схема варианта пересчитывается: `geometry` ещё от прошлых значений полей. */
export type PassportVariant = { key: string; label: string; geometry: BlastGeometryResponse | null; pending?: boolean };

export function PassportBar({
  variants,
  objectName,
  onOpenEconomics,
}: {
  /** Варианты заряда с их блоками: в паспорт уходит выбранный пользователем. */
  variants: PassportVariant[];
  /** Активный объект работ страницы: и адрес нового паспорта, и фильтр списка. */
  objectName: string;
  onOpenEconomics?: (passportId: string) => void;
}) {
  const [passports, setPassports] = useState<TechnicalPassport[]>([]);
  const [sites, setSites] = useState<{ code: string; name: string }[]>([]);
  // Справочник объектов получен (пусть даже пустым). Без этого флага пустой
  // каталог не отличить от ещё не пришедшего ответа, а разница видна
  // пользователю: объект в шапке может быть значением Cost V1 по умолчанию,
  // которого в справочнике нет вовсе — тогда сохранять некуда, и об этом
  // нужно сказать, а не молча выключить кнопку.
  const [sitesLoaded, setSitesLoaded] = useState(false);
  const [passportName, setPassportName] = useState("");
  const [variantKey, setVariantKey] = useState(variants[0]?.key ?? "");
  // Паспорт, выбранный в списке сохранённых. Пустой или исчезнувший из
  // списка — действует первый в списке.
  const [selectedId, setSelectedId] = useState("");
  const [busy, setBusy] = useState(false);
  // Паспорт, который сейчас удаляется: блокируем кнопку, пока идёт запрос.
  const [deletingId, setDeletingId] = useState("");
  const [error, setError] = useState("");
  const variant = variants.find((item) => item.key === variantKey) ?? variants[0];
  const geometry = variant?.geometry ?? null;
  // Пока схема пересчитывается, на экране блок прошлых значений полей —
  // сохранить его в паспорт значило бы отправить в экономику не то, что видно.
  const pending = Boolean(variant?.pending);
  const selected = passports.find((item) => item.id === selectedId) ?? passports[0] ?? null;
  // Объект работ из шапки — в справочнике он же «карьер/объект» с кодом.
  // Пока справочник не загружен, кода нет: сохранять и грузить список нечего.
  const siteCode = useMemo(
    () => sites.find((site) => site.name === objectName)?.code ?? "",
    [sites, objectName],
  );
  const siteMissing = sitesLoaded && !siteCode;
  // Актуальный код объекта для асинхронных обработчиков: пока идёт запрос,
  // объект в шапке могли переключить, и ответ по прошлому объекту в список
  // нового попадать не должен.
  const siteCodeRef = useRef(siteCode);
  siteCodeRef.current = siteCode;

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
        setSitesLoaded(true);
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

  async function savePassport() {
    if (!geometry || !siteCode) return;
    const requestedSite = siteCode;
    setBusy(true);
    setError("");
    try {
      const created = await api.economics.createTechnicalPassport({
        site_code: requestedSite,
        object_name: passportName.trim() || `Блок ${Math.round(geometry.block.block_volume_m3)} м³`,
        block: geometry.block as unknown as Record<string, unknown>,
        selected_variant: { label: geometry.label },
      });
      setPassportName("");
      // Объект мог смениться, пока шёл запрос: список уже показывает другой
      // объект, и созданный паспорт в него не относится.
      if (siteCodeRef.current !== requestedSite) return;
      setPassports((rows) => [created, ...rows]);
      setSelectedId(created.id);
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
      <header>
        <b>Технические паспорта</b>
        <span>{passports.length ? `${passports.length} по объекту` : "нет по объекту"}</span>
      </header>
      <div className="panel-body passport-fields">
        {error && <div className="page-error" role="alert">{error}</div>}
        {siteMissing && (
          <div className="page-error" role="alert">
            Объекта «{objectName}» нет в справочнике «Карьеры и объекты» — паспорт сохранить не по
            чему. Выберите другой объект в шапке или заведите этот в справочниках.
          </div>
        )}
        <label>
          Название паспорта
          <input
            value={passportName}
            placeholder="Блок, м³"
            onChange={(event) => setPassportName(event.target.value)}
          />
        </label>
        <div className="passport-line">
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
          <button
            type="button"
            className="secondary-button"
            onClick={() => void savePassport()}
            disabled={busy || pending || !geometry || !siteCode}
          >
            Сохранить паспорт
          </button>
        </div>
        {pending && <p className="passport-hint">Схема заряда пересчитывается…</p>}
        {!pending && geometry && variant && (
          // В паспорт уходит блок выбранного варианта с его зарядом и недозарядом —
          // показываем это до сохранения, чтобы масса не была сюрпризом. Что делает
          // кнопка «Экономика» — в справке листа (`CalcHelp`).
          <p className="passport-hint">
            В паспорт пойдёт «{variant.label}»:{" "}
            {Math.round(geometry.block.total_charge_mass_kg).toLocaleString("ru-RU")} кг ВВ,{" "}
            {geometry.block.total_holes} скважин, {Math.round(geometry.block.drilling_footage_m).toLocaleString("ru-RU")} п.м.,{" "}
            {geometry.block.specific_q_kg_m3.toFixed(2)} кг/м³ с доп. скважинами.
          </p>
        )}
        <div className="passport-line passport-saved">
          <label>
            Сохранённые паспорта
            <select
              value={selected?.id ?? ""}
              onChange={(event) => setSelectedId(event.target.value)}
              disabled={!passports.length}
            >
              {passports.length === 0 && <option value="">Сохранённых паспортов по этому объекту нет</option>}
              {passports.map((passport) => (
                <option key={passport.id} value={passport.id}>
                  {passport.object_name} ·{" "}
                  {Math.round(Number(passport.physical.explosive_kg ?? 0)).toLocaleString("ru-RU")} кг ВВ ·{" "}
                  {/* Дата и версия различают паспорта одного блока с одинаковым названием. */}
                  {new Date(passport.created_at).toLocaleDateString("ru-RU")} · вер. {passport.version_no}
                </option>
              ))}
            </select>
          </label>
          <button
            type="button"
            className="secondary-button"
            onClick={() => selected && onOpenEconomics?.(selected.id)}
            disabled={!selected || !onOpenEconomics}
          >
            Экономика
          </button>
          <button
            type="button"
            className="danger-button"
            onClick={() => selected && void removePassport(selected)}
            disabled={!selected || deletingId === selected.id}
            title="Удалить выбранный паспорт из списка"
          >
            {selected && deletingId === selected.id ? "Удаление…" : "Удалить"}
          </button>
        </div>
      </div>
    </section>
  );
}
