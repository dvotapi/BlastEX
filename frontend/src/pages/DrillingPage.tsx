import { useEffect } from "react";
import { useWorkspace } from "../app/useWorkspace";
import { useBlockEconomicsSessionContext } from "./economics/BlockEconomicsSessionContext";
import { DrillingPayrollPanel } from "./economics/drilling/DrillingPayrollPanel";
import { DrillingPriceDrivers } from "./economics/drilling/DrillingPriceDrivers";
import { RigPlanShiftsSlider, rigShiftNorm } from "./economics/drilling/RigPlanShiftsSlider";
import { amount, money } from "./economics/format";

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
    recalculating,
    passport,
    siteLabel,
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
          {params && defaults && (
            <section className="panel drilling-rig-load" aria-label="Загрузка станка">
              <h3>Загрузка станка</h3>
              {params.drilling_executor === "OWN" ? (
                <>
                  <RigPlanShiftsSlider
                    value={params.rig_plan_shifts}
                    norm={rigShiftNorm(defaults, params.rig_code)}
                    rubPerM={rubPerM}
                    rubPerMStale={recalculating}
                    disabled={!canEdit}
                    onChange={(value) => activeDraft && patchDraft(activeDraft.id, { rig_plan_shifts: value })}
                  />
                  <p>
                    Амортизация, страховка, ТОиР и запчасти станка делятся на плановые смены месяца: больше смен — дешевле
                    метр. Это тот же параметр, что в карточке бурения «Экономики блока».
                  </p>
                </>
              ) : (
                <p>Бурение отдано субподряду: постоянные затраты станка на блок не распределяются, загрузка станка цену метра не меняет.</p>
              )}
            </section>
          )}
          {params && defaults && params.drilling_executor === "OWN" && (
            <DrillingPriceDrivers passportId={selectedPassport} params={params} />
          )}
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
    </div>
  );
}
