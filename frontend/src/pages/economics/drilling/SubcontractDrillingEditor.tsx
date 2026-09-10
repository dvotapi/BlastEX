/**
 * Бурение субподрядом: подрядчик и его тариф — из справочника
 * `subcontract_rates`, либо ручная ставка (проверить предложение подрядчика
 * без публикации в справочник). Ручная ставка — черновик: сметчик может
 * опубликовать её отдельной кнопкой, после чего вкладка сама переключается
 * на опубликованный тариф.
 */
import { useState } from "react";
import { api } from "../../../api/endpoints";
import type { ValueOrigin } from "../../../types/blockEconomics";
import { CatalogSelect, type CatalogOption } from "../estimate/CatalogSelect";
import { EstimateLine } from "../estimate/EstimateLine";
import { NumericInput } from "../NumericInput";
import { OriginBadge } from "../estimate/OriginBadge";
import { lineNumber } from "../estimateModel";
import { lineByCode, lineShare } from "../sections/lineHelpers";
import type { SectionEditorProps } from "../sections/types";

export type SubcontractDrillingEditorProps = SectionEditorProps & {
  /** Каталог устарел и его нужно перечитать — зовётся сразу после публикации тарифа в справочник. */
  onDefaultsChanged: () => void;
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

  return (
    <>
      <EstimateLine
        number={lineNumber(group, 0)}
        name={
          <div className="subcontract-drilling-name">
            <CatalogSelect
              id="drilling-counterparty"
              label="Подрядчик"
              value={counterpartyCode}
              options={counterpartyOptions}
              onChange={selectCounterparty}
              disabled={!canEdit}
            />
            <CatalogSelect
              id="drilling-rate"
              label="Тариф"
              value={params.subcontract_rate_code ?? ""}
              options={rateCatalogOptions}
              onChange={selectRate}
              disabled={!canEdit || !counterpartyCode}
            />
          </div>
        }
        origin="PASSPORT"
        quantity={drillingM === null ? null : Number(drillingM)}
        unit="м"
        price={priceValue === null ? null : Number(priceValue)}
        amount={line?.amount_rub ?? 0}
        volume={volume}
        share={line ? lineShare(line, economics) : 0}
        formula={line?.formula}
        actions={
          <label className="drilling-rate-manual">
            Ставка, ₽/м
            <NumericInput
              value={priceValue}
              allowEmpty
              min={0}
              ariaLabel="Ставка субподряда, ₽/м"
              onChange={(value) => onChange({ subcontract_rate_rub: value })}
            />
            <OriginBadge origin={priceOrigin} />
          </label>
        }
      />
      {needsCounterpartyToSave && (
        <div className="drilling-rate-save">
          <button type="button" className="link-button" disabled title="Сначала выберите подрядчика">
            Сохранить тариф в справочник
          </button>
        </div>
      )}
      {canSave && (
        <div className="drilling-rate-save">
          {!saveOpen ? (
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
              <input
                type="text"
                aria-label="Название тарифа"
                value={rateName}
                onChange={(e) => setRateName(e.target.value)}
              />
              <button type="button" disabled={saving || !rateName.trim()} onClick={submitSave}>
                {saving ? "Сохраняем…" : "Сохранить"}
              </button>
              <button type="button" disabled={saving} onClick={() => setSaveOpen(false)}>
                Отмена
              </button>
            </div>
          )}
          {status && <p className="drilling-rate-status">{status}</p>}
          {error && (
            <p className="drilling-rate-error" role="alert">
              {error}
            </p>
          )}
        </div>
      )}
      {otherLines.map((item, index) => (
        <EstimateLine
          key={item.cost_item_code}
          number={`${lineNumber(group, 0)}.${index + 1}`}
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
