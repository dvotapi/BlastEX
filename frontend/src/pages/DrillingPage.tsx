import { useEffect, useState } from "react";
import { useWorkspace } from "../app/useWorkspace";
import { useBlockEconomicsSessionContext } from "./economics/BlockEconomicsSessionContext";
import { DrillingPayrollPanel } from "./economics/drilling/DrillingPayrollPanel";
import { amount, money } from "./economics/format";
import { LegacyDrillingCalculator } from "./LegacyDrillingCalculator";

/**
 * Подэтап «Бурение» комплекса БВР. Работает с тем же активным черновиком, что
 * и «Экономика блока»: объём, станок и объект берутся оттуда, а зарплата
 * экипажа настраивается здесь.
 */
export function DrillingPage() {
  const { canEdit } = useWorkspace();
  const {
    selectedPassport,
    error,
    defaults,
    activeDraft,
    activeEconomics,
    passport,
    siteLabel,
    patchDraft,
    refresh,
    dirty,
    busy,
    saveActive,
  } = useBlockEconomicsSessionContext();
  const [legacyOpen, setLegacyOpen] = useState(false);

  // Зашли на страницу заново: справочники могли обновиться, пока сессия жила дальше.
  useEffect(() => {
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const params = activeDraft?.parameters ?? null;
  const rigName = params && defaults ? defaults.rigs.find((rig) => rig.code === params.rig_code)?.name : undefined;
  const drillingM = defaults?.passport.physical.drilling_m ?? null;
  const rubPerM = activeEconomics?.natural.values.drilling_rub_per_m;

  return (
    <div className="page-content drilling-page">
      <h2>Бурение</h2>
      {error && (
        <div className="page-error" role="alert">
          {error}
        </div>
      )}
      {!selectedPassport ? (
        <p className="page-caption">
          Сохранённых технических паспортов нет. Сохраните паспорт на вкладке «Расчёт БВР» — бурение блока считается по нему.
        </p>
      ) : (
        <>
          <p className="page-caption">
            Объём берётся из паспорта блока, станок и тип исполнения — из сметы («Экономика блока»). Зарплату экипажа настройте ниже.
          </p>
          <dl className="drilling-block-facts" aria-label="Блок">
            <div>
              <dt>Паспорт</dt>
              <dd>{passport ? `вер. ${passport.version_no} · ${siteLabel}` : "—"}</dd>
            </div>
            <div>
              <dt>Объём бурения</dt>
              <dd>{drillingM === null ? "—" : `${amount(Number(drillingM))} п.м.`}</dd>
            </div>
            <div>
              <dt>Станок</dt>
              <dd>{rigName ?? params?.rig_code ?? "—"}</dd>
            </div>
            <div>
              <dt>Стоимость 1 п.м. в смете</dt>
              <dd>{rubPerM === undefined ? "—" : `${money(Number(rubPerM))} ₽/м`}</dd>
            </div>
          </dl>
          {params ? (
            <DrillingPayrollPanel
              params={params}
              economics={activeEconomics}
              canEdit={canEdit}
              onChange={(patch) => activeDraft && patchDraft(activeDraft.id, patch)}
            />
          ) : (
            <p className="page-caption">Расчёт блока загружается…</p>
          )}
          {activeDraft && (
            <div className="drilling-save">
              <button type="button" disabled={!canEdit || !dirty || busy} onClick={() => void saveActive(activeDraft.name)}>
                Сохранить сценарий блока
              </button>
              <span>
                {dirty
                  ? "Сценарий блока не сохранён. Источник ФОТ и другие параметры блока хранятся в нём, кнопка «Сохранить» вверху их не сохраняет."
                  : "Сценарий блока сохранён."}
              </span>
            </div>
          )}
        </>
      )}

      <details className="panel drilling-legacy" onToggle={(event) => setLegacyOpen(event.currentTarget.open)}>
        <summary>Калькулятор цены п.м. для листа «Расчёт» (Excel-смета)</summary>
        {/* Считает по запросу только раскрытым: свёрнутому он ни к чему. */}
        {legacyOpen && <LegacyDrillingCalculator />}
      </details>
    </div>
  );
}
