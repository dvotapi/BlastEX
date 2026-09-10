/**
 * Бурение субподрядом: подрядчик и его тариф — из справочника
 * `subcontract_rates`, либо ручная ставка (проверить предложение подрядчика
 * без публикации в справочник). Ручная ставка — черновик: сметчик может
 * опубликовать её отдельной кнопкой, после чего вкладка сама переключается
 * на опубликованный тариф.
 */
import { useState, type ReactNode } from "react";
import { api } from "../../../api/endpoints";
import type { ValueOrigin } from "../../../types/blockEconomics";
import { CatalogSelect, type CatalogOption } from "../estimate/CatalogSelect";
import { EstimateLine } from "../estimate/EstimateLine";
import { NumericInput } from "../NumericInput";
import { lineNumber } from "../estimateModel";
import { amount as formatAmount } from "../format";
import { lineByCode, lineShare } from "../sections/lineHelpers";
import type { SectionEditorProps } from "../sections/types";
import { DrillingCard, type DrillingFact } from "./DrillingCard";

export type SubcontractDrillingEditorProps = SectionEditorProps & {
  /** Каталог устарел и его нужно перечитать — зовётся сразу после публикации тарифа в справочник. */
  onDefaultsChanged: () => void;
  /** Переключатель «Исполнение» — рисует `DrillingSection`, показывает карточка. */
  executor: ReactNode;
};

export function SubcontractDrillingEditor({
  group,
  params,
  defaults,
  economics,
  volume,
  canEdit,
  onChange,
  onDefaultsChanged,
  executor,
}: SubcontractDrillingEditorProps) {
  const selectedRate = defaults.subcontract_rates.find((rate) => rate.code === params.subcontract_rate_code);

  // Подрядчик — контекст выбора тарифа, в параметрах прогона своего поля не
  // имеет: как только тариф выбран, подрядчик виден по его `counterparty_code`.
  const [counterpartyCode, setCounterpartyCode] = useState<string>(
    selectedRate?.counterparty_code ?? defaults.counterparties[0]?.code ?? "",
  );

  const [saveOpen, setSaveOpen] = useState(false);
  const [rateName, setRateName] = useState("");
  const [saving, setSaving] = useState(false);
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const counterpartyOptions: CatalogOption[] = defaults.counterparties.map((c) => ({ code: c.code, name: c.name }));
  const rateOptions = defaults.subcontract_rates.filter((rate) => rate.counterparty_code === counterpartyCode);
  const rateCatalogOptions: CatalogOption[] = rateOptions.map((rate) => ({
    code: rate.code,
    name: rate.name,
    price: rate.rate_rub,
    unit: rate.unit,
  }));

  function selectCounterparty(code: string) {
    setCounterpartyCode(code);
    onChange({ subcontract_rate_code: null, subcontract_rate_rub: null });
  }

  function selectRate(code: string) {
    onChange({ subcontract_rate_code: code, subcontract_rate_rub: null });
  }

  const priceValue = params.subcontract_rate_rub ?? selectedRate?.rate_rub ?? null;
  const priceOrigin: ValueOrigin = params.subcontract_rate_rub !== null ? "MANUAL" : selectedRate ? "REFERENCE" : "";

  const line = lineByCode(group.lines, "DRILL_SUBCONTRACT");
  const drillingM = defaults.passport.physical.drilling_m ?? null;
  const otherLines = group.lines.filter((item) => item.cost_item_code !== "DRILL_SUBCONTRACT");

  // Подрядчик не выбран (справочник пуст либо выбор не сделан) — бэкенд
  // требует `counterparty_code` непусто (min_length=1) и отклонит публикацию
  // тарифа без него, так что кнопку показываем недоступной, а не отправляем
  // запрос, который заведомо упадёт с 422.
  const hasCounterparty = counterpartyCode !== "";
  const canSave = params.subcontract_rate_rub !== null && canEdit && hasCounterparty;
  const needsCounterpartyToSave = params.subcontract_rate_rub !== null && canEdit && !hasCounterparty;

  async function submitSave() {
    if (params.subcontract_rate_rub === null || !hasCounterparty) return;
    setSaving(true);
    setError(null);
    try {
      const response = await api.blockEconomics.subcontractRateToReference({
        counterparty_code: counterpartyCode,
        operation_code: "PRODUCTION_DRILLING",
        name: rateName.trim() || (selectedRate?.name ?? "Тариф субподряда бурения"),
        unit: "M",
        rate_rub: params.subcontract_rate_rub,
      });
      onChange({ subcontract_rate_code: response.code, subcontract_rate_rub: null });
      // Каталог (`defaults.subcontract_rates`) — снимок ДО публикации: без
      // перезагрузки только что опубликованный код не находится в нём, и
      // выбор тарифа выглядит так, будто пропал (сброшен на «не выбрано»).
      onDefaultsChanged();
      setStatus(`Тариф «${response.code}» опубликован ревизией ${response.reference_revision_id}`);
      setSaveOpen(false);
      setRateName("");
    } catch (err) {
      const detail = err instanceof Error && err.message ? err.message : null;
      setError(detail ? `Не удалось сохранить тариф в справочник: ${detail}` : "Не удалось сохранить тариф в справочник");
    } finally {
      setSaving(false);
    }
  }

  // Форма публикации тарифа живёт под карточкой: разметка `.drilling-rate-save-form`
  // сохранена дословно — на неё опирается тест страницы.
  const saveForm = !saveOpen ? (
    <button
      type="button"
      className="link-button"
      onClick={() => {
        setSaveOpen(true);
        setRateName(selectedRate?.name ?? "");
      }}
    >
      Сохранить тариф в справочник
    </button>
  ) : (
    <div className="drilling-rate-save-form">
      <input type="text" aria-label="Название тарифа" value={rateName} onChange={(e) => setRateName(e.target.value)} />
      <button type="button" disabled={saving || !rateName.trim()} onClick={submitSave}>
        {saving ? "Сохраняем…" : "Сохранить"}
      </button>
      <button type="button" disabled={saving} onClick={() => setSaveOpen(false)}>
        Отмена
      </button>
    </div>
  );

  const facts: DrillingFact[] = [
    {
      label: "Объём бурения",
      value: drillingM === null ? "—" : `${formatAmount(Number(drillingM))} п.м.`,
      origin: "PASSPORT",
      originLabel: "Из паспорта",
    },
    {
      label: "Ставка, ₽/м",
      editor: (
        <NumericInput
          value={priceValue}
          allowEmpty
          min={0}
          ariaLabel="Ставка субподряда, ₽/м"
          disabled={!canEdit}
          onChange={(value) => onChange({ subcontract_rate_rub: value })}
        />
      ),
      origin: priceOrigin,
    },
  ];

  return (
    <>
      <DrillingCard
        executor={executor}
        machine={
          <>
            <label className="drilling-card-field">
              Подрядчик
              <CatalogSelect
                id="drilling-counterparty"
                label="Подрядчик"
                value={counterpartyCode}
                options={counterpartyOptions}
                onChange={selectCounterparty}
                disabled={!canEdit}
                variant="field"
              />
            </label>
            <label className="drilling-card-field">
              Тариф
              <CatalogSelect
                id="drilling-rate"
                label="Тариф"
                value={params.subcontract_rate_code ?? ""}
                options={rateCatalogOptions}
                onChange={selectRate}
                disabled={!canEdit || !counterpartyCode}
                variant="field"
              />
            </label>
          </>
        }
        facts={facts}
        amount={line?.amount_rub ?? 0}
        volume={volume}
        formula={line?.formula}
        footer={
          // Статус и ошибка публикации стоят рядом с формой, но НЕ под её
          // условием: удачная публикация сама обнуляет ручную ставку, из-за
          // чего `canSave` становится ложным — и сообщение «Тариф опубликован
          // ревизией …» исчезало вместе с формой, ни разу не показавшись.
          <div className="drilling-rate-save">
            {needsCounterpartyToSave && (
              <button type="button" className="link-button" disabled title="Сначала выберите подрядчика">
                Сохранить тариф в справочник
              </button>
            )}
            {canSave && saveForm}
            {status && <p className="drilling-rate-status">{status}</p>}
            {error && (
              <p className="drilling-rate-error" role="alert">
                {error}
              </p>
            )}
          </div>
        }
      />
      {otherLines.map((item, index) => (
        <EstimateLine
          key={item.cost_item_code}
          number={lineNumber(group, index)}
          name={item.cost_item_name}
          origin={item.price_origin || item.quantity_origin}
          quantity={item.quantity}
          unit={item.unit}
          price={item.unit_price_rub}
          amount={item.amount_rub}
          volume={volume}
          share={lineShare(item, economics)}
          formula={item.formula}
        />
      ))}
    </>
  );
}
