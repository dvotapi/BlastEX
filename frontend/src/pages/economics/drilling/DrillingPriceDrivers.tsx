/**
 * Панель «Что двигает цену метра» страницы «Бурение».
 *
 * Сервер (`POST /economics/block-economics/drilling-sensitivity`) ранжирует
 * ручки цены метра по эффекту ±10 % и отдаёт шкалу сдельной премии машиниста;
 * панель показывает четыре самых сильных ручки и всегда — блок «Премия
 * машинистов», у каждой бегунок «что если» (`WhatIfSlider`). Пробные значения
 * живут в состоянии панели и уходят только в
 * `POST /economics/block-economics/drilling-what-if`, который подменяет их в
 * памяти запроса: ни черновик, ни справочники не меняются, уход со страницы
 * всё сбрасывает. Плановые смены станка — настоящий параметр черновика с
 * бегунком «Загрузка станка», поэтому в ранжировании они показываются, а
 * пробного бегунка у них нет.
 *
 * Цены — себестоимость метра (без ОХР и рентабельности), как «Стоимость
 * 1 п.м.» на странице: без ФОТ (строки станка) и с ФОТ экипажа бурения.
 */
import { useEffect, useMemo, useRef, useState } from "react";
import { api } from "../../../api/endpoints";
import type {
  DrillingKnob,
  DrillingPrices,
  DrillingSensitivity,
  DrillingWhatIf,
  ModelParameters,
} from "../../../types/blockEconomics";
import { money } from "../format";
import { WhatIfSlider, effectText } from "./WhatIfSlider";

/** Сколько самых сильных ручек показывать, не считая премии. */
export const TOP_KNOBS = 4;
/** Пауза после правки черновика до запроса ранжирования — как у пересчёта блока. */
export const RANKING_DELAY_MS = 300;

/** Шаг границ шкалы премии: потолок строго выше нормы. */
const SCALE_GAP = 1;

export type DrillingPriceDriversProps = {
  passportId: string;
  params: ModelParameters;
};

export type Overrides = Record<string, number>;

/**
 * Границы бегунков шкалы премии по правилам справочника (`LaborRatePayload`):
 * норма ниже потолка, расценка на потолке не ниже расценки на норме.
 * Границы считаются по текущим (пробным или справочным) значениям соседних ручек.
 */
export function premiumBounds(knobs: DrillingKnob[], overrides: Overrides): Record<string, { min?: number; max?: number }> {
  const current = (code: string) => {
    const knob = knobs.find((item) => item.code === code);
    if (!knob) return undefined;
    return overrides[code] ?? knob.base_value;
  };
  const norm = current("PREMIUM_NORM");
  const ceiling = current("PREMIUM_CEILING");
  const rateNorm = current("PREMIUM_RATE_NORM");
  const rateCeiling = current("PREMIUM_RATE_CEILING");
  const bounds: Record<string, { min?: number; max?: number }> = {};
  if (ceiling !== undefined) bounds.PREMIUM_NORM = { max: ceiling - SCALE_GAP };
  if (norm !== undefined) bounds.PREMIUM_CEILING = { min: norm + SCALE_GAP };
  if (rateCeiling !== undefined) bounds.PREMIUM_RATE_NORM = { max: rateCeiling };
  if (rateNorm !== undefined) bounds.PREMIUM_RATE_CEILING = { min: rateNorm };
  return bounds;
}

function priceText(value: number | null | undefined): string {
  return value === null || value === undefined ? "—" : `${money(value)} ₽/м`;
}

function deltaText(current: number | null | undefined, base: number | null | undefined): string {
  if (current === null || current === undefined || base === null || base === undefined) return "";
  const delta = current - base;
  if (Math.abs(delta) < 0.005) return "как в смете";
  return `${delta > 0 ? "+" : "−"}${money(Math.abs(delta))} ₽/м к смете`;
}

export function DrillingPriceDrivers({ passportId, params }: DrillingPriceDriversProps) {
  const [ranking, setRanking] = useState<DrillingSensitivity | null>(null);
  const [rankingBusy, setRankingBusy] = useState(false);
  const [overrides, setOverrides] = useState<Overrides>({});
  const [whatIf, setWhatIf] = useState<DrillingWhatIf | null>(null);
  const [whatIfBusy, setWhatIfBusy] = useState(false);
  const [error, setError] = useState("");
  // Последний запрос упал: числа на экране не отвечают текущим ручкам, и
  // показывать прежний результат как актуальный нельзя — только «—» и ошибку.
  const [failed, setFailed] = useState(false);
  const rankingRequest = useRef(0);
  const whatIfRequest = useRef(0);

  // Ранжирование — по черновику с той же задержкой, что пересчёт блока: сметчик
  // двигает параметры, а не жмёт «Рассчитать».
  useEffect(() => {
    if (!passportId) return;
    const id = ++rankingRequest.current;
    setRankingBusy(true);
    const timer = window.setTimeout(() => {
      api.blockEconomics
        .drillingSensitivity(passportId, params)
        .then((response) => {
          if (id !== rankingRequest.current) return;
          setRanking(response);
          // Ручки, которых в новом ранжировании нет (сменили станок или условие),
          // теряют пробные значения: иначе каждый «что если» отвечал бы 422.
          const known = new Set([...response.knobs, ...(response.premium?.knobs ?? [])].map((knob) => knob.code));
          setOverrides((current) => {
            const kept = Object.fromEntries(Object.entries(current).filter(([code]) => known.has(code)));
            return Object.keys(kept).length === Object.keys(current).length ? current : kept;
          });
          setRankingBusy(false);
          setFailed(false);
          setError("");
        })
        .catch((reason) => {
          if (id !== rankingRequest.current) return;
          setRankingBusy(false);
          setFailed(true);
          setError(reason instanceof Error ? reason.message : "Не удалось посчитать ручки цены метра.");
        });
    }, RANKING_DELAY_MS);
    return () => window.clearTimeout(timer);
  }, [passportId, params]);

  // «Что если» — сразу по отпусканию бегунка (само отпускание уже отфильтровало
  // движение); пустые подмены — цена из ранжирования, запрос не нужен.
  const overridesKey = JSON.stringify(overrides);
  useEffect(() => {
    const id = ++whatIfRequest.current;
    if (!passportId || Object.keys(overrides).length === 0) {
      setWhatIf(null);
      setWhatIfBusy(false);
      setFailed(false);
      setError("");
      return;
    }
    setWhatIfBusy(true);
    api.blockEconomics
      .drillingWhatIf(passportId, params, overrides)
      .then((response) => {
        if (id !== whatIfRequest.current) return;
        setWhatIf(response);
        setWhatIfBusy(false);
        setFailed(false);
        setError("");
      })
      .catch((reason) => {
        if (id !== whatIfRequest.current) return;
        // Прежний результат отвечал другим ручкам: убираем, иначе разница «к
        // смете» останется на экране рядом с новыми значениями бегунков.
        setWhatIf(null);
        setWhatIfBusy(false);
        setFailed(true);
        setError(reason instanceof Error ? reason.message : "Не удалось посчитать пробную цену метра.");
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [passportId, params, overridesKey]);

  const premiumKnobs = ranking?.premium?.knobs ?? [];
  const bounds = useMemo(() => premiumBounds(premiumKnobs, overrides), [premiumKnobs, overrides]);

  function setOverride(code: string, value: number | null) {
    setOverrides((current) => {
      const next = { ...current };
      if (value === null) delete next[code];
      else next[code] = value;
      return next;
    });
  }

  const base: DrillingPrices | null = whatIf?.base ?? ranking?.base ?? null;
  const shown: DrillingPrices | null = failed ? null : whatIf?.result ?? ranking?.base ?? null;
  const hasOverrides = Object.keys(overrides).length > 0;
  // Черновик изменился, ответ ранжирования ещё не пришёл — цены на экране от прежних параметров.
  const stale = whatIfBusy || rankingBusy;
  const top = (ranking?.knobs ?? []).slice(0, TOP_KNOBS);
  const premium = ranking?.premium ?? null;

  return (
    <section className="panel drilling-price-drivers" aria-label="Что двигает цену метра">
      <h3>Что двигает цену метра</h3>
      <p className="what-if-note">
        Пробные значения: в смету и справочники не пишутся. Бегунки показывают, как цена метра отзывается на самые
        сильные ручки; при уходе со страницы всё возвращается к справочнику.
      </p>
      {error && (
        <p className="what-if-error" role="alert">
          {error}
        </p>
      )}
      <dl className={`what-if-prices${stale ? " is-stale" : ""}`} aria-label="Цена метра">
        <div>
          <dt>Без ФОТ</dt>
          <dd>
            <b>{priceText(shown?.without_payroll_rub_per_m)}</b>
            {stale && <span className="what-if-stale"> считается…</span>}
            {hasOverrides && !stale && (
              <span className="what-if-delta"> {deltaText(shown?.without_payroll_rub_per_m, base?.without_payroll_rub_per_m)}</span>
            )}
          </dd>
        </div>
        <div>
          <dt>С ФОТ экипажа</dt>
          <dd>
            <b>{priceText(shown?.with_payroll_rub_per_m)}</b>
            {stale && <span className="what-if-stale"> считается…</span>}
            {hasOverrides && !stale && (
              <span className="what-if-delta"> {deltaText(shown?.with_payroll_rub_per_m, base?.with_payroll_rub_per_m)}</span>
            )}
          </dd>
        </div>
      </dl>
      {ranking === null && !error && <p className="page-caption">Ранжирование ручек считается…</p>}
      {ranking !== null && shown !== null && shown.without_payroll_rub_per_m === null && (
        <p className="page-caption">Бурение не посчитано: нет нормы бурения у станка или метров бурения.</p>
      )}
      {top.length > 0 && (
        <div className="what-if-group">
          <h4>Самые сильные ручки</h4>
          {top.map((knob) =>
            knob.draft_param ? (
              <div className="what-if-knob is-draft" key={knob.code} data-knob={knob.code}>
                <div className="what-if-knob-head">
                  <span className="what-if-knob-label">{knob.label}</span>
                  <span className="what-if-knob-effect">{effectText(knob.delta_rub_per_m)}</span>
                </div>
                <div className="what-if-knob-caption">
                  <span>Параметр черновика: меняется бегунком «Загрузка станка» выше.</span>
                </div>
              </div>
            ) : (
              <WhatIfSlider
                key={knob.code}
                code={knob.code}
                label={knob.label}
                unit={knob.unit}
                base={knob.base_value}
                value={overrides[knob.code] ?? null}
                deltaRubPerM={knob.delta_rub_per_m}
                onChange={(value) => setOverride(knob.code, value)}
              />
            ),
          )}
        </div>
      )}
      {ranking !== null && (
        <div className="what-if-group what-if-premium">
          <h4>Премия машинистов</h4>
          {premium === null ? (
            <p className="page-caption">
              У экипажа бурения нет ставки со шкалой сдельной премии: заведите шкалу в «Ставках персонала».
            </p>
          ) : (
            <>
              <p className="page-caption">
                Шкала ставки «{premium.position_name}»
                {premium.applies ? "." : `. ${premium.note}`}
              </p>
              {premium.knobs.map((knob) => (
                <WhatIfSlider
                  key={knob.code}
                  code={knob.code}
                  label={knob.label}
                  unit={knob.unit}
                  base={knob.base_value}
                  value={overrides[knob.code] ?? null}
                  min={bounds[knob.code]?.min}
                  max={bounds[knob.code]?.max}
                  deltaRubPerM={premium.applies ? knob.delta_rub_per_m : null}
                  inactive={!premium.applies}
                  onChange={(value) => setOverride(knob.code, value)}
                />
              ))}
            </>
          )}
        </div>
      )}
      {hasOverrides && (
        <button type="button" className="link-button what-if-reset-all" onClick={() => setOverrides({})}>
          Вернуть все к справочнику
        </button>
      )}
    </section>
  );
}
