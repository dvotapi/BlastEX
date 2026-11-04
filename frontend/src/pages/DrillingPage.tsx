import { useEffect } from "react";
import { useWorkspace } from "../app/useWorkspace";
import { useBlockEconomicsSessionContext } from "./economics/BlockEconomicsSessionContext";
import { DrillingPayrollBreakdown, DrillingPayrollSource } from "./economics/drilling/DrillingPayrollPanel";
import { DrillingPriceDrivers } from "./economics/drilling/DrillingPriceDrivers";
import { DrillingTopbar } from "./economics/drilling/DrillingTopbar";
import { RigPlanShiftsSlider, rigShiftNorm } from "./economics/drilling/RigPlanShiftsSlider";
import { amount, money } from "./economics/format";

/**
 * Подэтап «Бурение» комплекса БВР. Работает с тем же активным черновиком, что
 * и «Экономика блока»: объём, станок и объект берутся оттуда, а зарплата
 * экипажа настраивается здесь.
 */
export function DrillingPage() {
  const { canEdit, state } = useWorkspace();
  // Полосы рабочего пространства на «Бурении» нет: предупреждения справочников —
  // здесь же, свёрнутым списком, иначе они пропали бы со страницы, где считаются.
  const referenceWarnings = state?.warnings ?? [];
  const {
    passports,
    selectedPassport,
    setSelectedPassport,
    siteLabel,
    error,
    defaults,
    activeDraft,
    activeEconomics,
    recalculating,
    passport,
    patchDraft,
    refresh,
    dirty,
    busy,
    saveActive,
  } = useBlockEconomicsSessionContext();

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
      {error && (
        <div className="page-error" role="alert">
          {error}
        </div>
      )}
      {referenceWarnings.length > 0 && (
        <details className="drilling-reference-warnings">
          <summary>Предупреждения справочников ({referenceWarnings.length})</summary>
          <ul>
            {referenceWarnings.map((warning) => (
              <li key={warning}>{warning}</li>
            ))}
          </ul>
        </details>
      )}
      {!selectedPassport ? (
        <p className="page-caption">
          Сохранённых технических паспортов нет. Сохраните паспорт на вкладке «Расчёт БВР» — бурение блока считается по нему.
        </p>
      ) : (
        <>
          <DrillingTopbar
            passports={passports}
            selectedId={selectedPassport}
            onSelect={setSelectedPassport}
            siteLabel={siteLabel}
            siteTitle={passport?.site_code}
            volumeLabel={drillingM === null ? "—" : `${amount(Number(drillingM))} п.м.`}
            rigLabel={rigName ?? params?.rig_code ?? "—"}
            priceLabel={rubPerM === undefined ? "—" : `${money(Number(rubPerM))} ₽/м`}
            priceStale={recalculating}
          />
          {params && defaults ? (
            <section className="panel drilling-rig-load" aria-label="Загрузка станка и ФОТ экипажа">
              <div className="drilling-rig-load-shifts">
                {params.drilling_executor === "OWN" ? (
                  <>
                    <h3 title="Амортизация, страховка, ТОиР и запчасти станка делятся на плановые смены месяца. Тот же параметр, что в карточке бурения «Экономики блока».">
                      Загрузка станка
                    </h3>
                    <RigPlanShiftsSlider
                      value={params.rig_plan_shifts}
                      norm={rigShiftNorm(defaults, params.rig_code)}
                      disabled={!canEdit}
                      onChange={(value) => activeDraft && patchDraft(activeDraft.id, { rig_plan_shifts: value })}
                    />
                  </>
                ) : (
                  <p>Бурение отдано субподряду: постоянные затраты станка на блок не распределяются, загрузка станка цену метра не меняет.</p>
                )}
              </div>
              <DrillingPayrollSource
                params={params}
                economics={activeEconomics}
                canEdit={canEdit}
                onChange={(patch) => activeDraft && patchDraft(activeDraft.id, patch)}
              />
              <DrillingPayrollBreakdown params={params} economics={activeEconomics} />
            </section>
          ) : (
            <p className="page-caption">Расчёт блока загружается…</p>
          )}
          {params && defaults && params.drilling_executor === "OWN" && (
            <DrillingPriceDrivers passportId={selectedPassport} params={params} />
          )}
          {activeDraft && (
            <div className="drilling-save">
              <button type="button" disabled={!canEdit || !dirty || busy} onClick={() => void saveActive(activeDraft.name)}>
                Сохранить сценарий блока
              </button>
              <span>
                {dirty
                  ? "Сценарий блока не сохранён. Источник ФОТ, загрузка станка и другие параметры блока хранятся в нём."
                  : "Сценарий блока сохранён."}
              </span>
            </div>
          )}
        </>
      )}
    </div>
  );
}
