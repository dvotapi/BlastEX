import { useEffect, useId, useRef, useState } from "react";
import { ruNumber } from "../../../lib/format";
import type { KuzRamCalibrateResponse, KuzRamCalibrationRow, KuzRamFactInput } from "../../../types";
import { trimmed } from "./kuzramFormat";
import {
  completeFacts,
  FACT_FIELDS,
  FACT_LABELS,
  factCellError,
  MAX_FACTS,
  parseDecimal,
  type FactField,
  type KuzRamFact,
} from "./kuzramSettings";

type Message = { tone: "ok" | "warn" | "error"; text: string };

/**
 * Ячейка факта. Хранит набранный текст: пустая ячейка допустима (строка просто
 * не идёт в подбор), неверное число подсвечивается и в подбор тоже не идёт.
 */
function FactCell({
  field,
  value,
  rowNumber,
  onCommit,
}: {
  field: FactField;
  value: number | null;
  rowNumber: number;
  onCommit: (value: number | null) => void;
}) {
  const id = useId();
  const [draft, setDraft] = useState(() => (value === null ? "" : trimmed(value, 6)));
  // Значение сменилось снаружи (удалили строку выше) — показываем новое;
  // свой незаконченный ввод не трогаем.
  useEffect(() => {
    setDraft((current) => (parseDecimal(current) === value ? current : value === null ? "" : trimmed(value, 6)));
  }, [value]);
  const error = draft.trim() !== "" && parseDecimal(draft) === null ? "Введите число." : factCellError(field, value);

  function change(text: string) {
    setDraft(text);
    const next = parseDecimal(text);
    if (next !== value) onCommit(next);
  }

  return (
    <>
      <input
        type="text"
        inputMode="decimal"
        autoComplete="off"
        aria-label={`${FACT_LABELS[field].label}, строка ${rowNumber}`}
        value={draft}
        aria-invalid={error ? true : undefined}
        aria-describedby={error ? `${id}-error` : undefined}
        onChange={(event) => change(event.target.value)}
      />
      {error && (
        <small id={`${id}-error`} className="kuzram-field-error">
          {error}
        </small>
      )}
    </>
  );
}

/**
 * Фактические взрывы объекта и подбор C(A). Строки хранятся за объектом вместе
 * с настройками и подбор сетки не запускают; «Подобрать C(A) по факту» шлёт
 * полные строки на сервер и записывает среднюю поправку в настройки.
 */
export function KuzRamFacts({
  facts,
  onChange,
  defaultCrownMm,
  onCalibrate,
  onApplyCorrection,
}: {
  facts: KuzRamFact[];
  onChange: (next: KuzRamFact[]) => void;
  /** Коронка новой строки — выбранная на листе. */
  defaultCrownMm: number | null;
  onCalibrate: (facts: KuzRamFactInput[]) => Promise<KuzRamCalibrateResponse>;
  /** Записать подобранную C(A) в настройки объекта. */
  onApplyCorrection: (value: number) => void;
}) {
  const [calibration, setCalibration] = useState<Map<number, KuzRamCalibrationRow> | null>(null);
  const [message, setMessage] = useState<Message | null>(null);
  const [pending, setPending] = useState(false);
  // Растёт при каждой правке строк: ответ подбора, начатого до правки, уже не про эти строки.
  const editRef = useRef(0);
  const complete = completeFacts(facts);

  function update(next: KuzRamFact[]) {
    editRef.current += 1;
    setCalibration(null);
    setMessage(null);
    onChange(next);
  }

  async function calibrate() {
    const rows = completeFacts(facts);
    if (!rows.length) return;
    const edit = editRef.current;
    setPending(true);
    setMessage(null);
    try {
      const response = await onCalibrate(rows.map((row) => row.fact));
      if (edit !== editRef.current) return;
      setCalibration(new Map(rows.map((row, index) => [row.index, response.rows[index]])));
      const skippedRows = facts.length - rows.length;
      const tail = skippedRows ? ` Неполные или неверные строки не учитывались: ${skippedRows}.` : "";
      if (response.rock_factor_correction === null) {
        setMessage({
          tone: "warn",
          text: `Ни одна строка не совпала с моделью при C(A) от 0,1 до 10 — поправка не изменена. Проверьте фактические данные.${tail}`,
        });
        return;
      }
      onApplyCorrection(response.rock_factor_correction);
      const skipped = response.skipped ? ` Пропущено строк: ${response.skipped} — для них нет C(A) от 0,1 до 10.` : "";
      setMessage({
        tone: "ok",
        text:
          `C(A) = ${trimmed(response.rock_factor_correction)} записана в настройки — посчитано по строкам: ` +
          `${response.used} из ${rows.length}.${skipped}${tail}`,
      });
    } catch (reason) {
      if (edit !== editRef.current) return;
      setMessage({ tone: "error", text: reason instanceof Error ? reason.message : "Не удалось подобрать C(A)." });
    } finally {
      setPending(false);
    }
  }

  return (
    <section className="kuzram-card" aria-labelledby="kuzram-facts-title">
      <h3 id="kuzram-facts-title">Фактические взрывы и подбор C(A)</h3>
      <p className="kuzram-facts-hint">
        Коронка, фактический удельный расход и фактический негабарит; порода, ВВ и уступ — с листа. Строки сохраняются
        за объектом и варианты сетки не пересчитывают — это делает только «Подобрать C(A) по факту».
      </p>
      <div className="kuzram-table-scroll">
        <table className="kuzram-table kuzram-facts">
          <thead>
            <tr>
              <th scope="col">Коронка, мм</th>
              <th scope="col">q факт, кг/м³</th>
              <th scope="col">Негабарит факт, %</th>
              <th scope="col" className="sep">До исправления, %</th>
              <th scope="col">Kuz-Ram, %</th>
              <th scope="col">C(A) строки</th>
              <th aria-label="Удалить" />
            </tr>
          </thead>
          <tbody>
            {facts.map((row, index) => {
              const result = calibration?.get(index);
              return (
                <tr key={index}>
                  {FACT_FIELDS.map((field) => (
                    <td key={field}>
                      <FactCell
                        field={field}
                        value={row[field]}
                        rowNumber={index + 1}
                        onCommit={(value) => update(facts.map((item, i) => (i === index ? { ...item, [field]: value } : item)))}
                      />
                    </td>
                  ))}
                  <td className="sep">{result ? ruNumber(result.legacy_oversize_pct, 2) : "—"}</td>
                  <td>{result ? ruNumber(result.model_oversize_pct, 2) : "—"}</td>
                  <td>
                    {!result ? "—" : result.rock_factor_correction === null ? (
                      <span title={result.note ?? undefined}>нет</span>
                    ) : (
                      trimmed(result.rock_factor_correction)
                    )}
                  </td>
                  <td>
                    <button
                      type="button"
                      className="kuzram-row-remove"
                      aria-label={`Удалить взрыв ${index + 1}`}
                      onClick={() => update(facts.filter((_, i) => i !== index))}
                    >
                      ×
                    </button>
                  </td>
                </tr>
              );
            })}
            {!facts.length && (
              <tr>
                <td colSpan={7} className="kuzram-empty">
                  Фактических взрывов пока нет.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
      {calibration && <p className="kuzram-facts-hint">Прогнозы моделей — при фактическом q и C(A), действовавшей до подбора.</p>}
      <div className="kuzram-facts-actions">
        <button
          type="button"
          className="secondary-button"
          disabled={facts.length >= MAX_FACTS}
          onClick={() => update([...facts, { crown_mm: defaultCrownMm, q_kg_m3: null, oversize_pct: null }])}
        >
          Добавить взрыв
        </button>
        <button type="button" className="primary-button" disabled={!complete.length || pending} onClick={() => void calibrate()}>
          {pending ? "Подбор C(A)…" : "Подобрать C(A) по факту"}
        </button>
        {facts.length >= MAX_FACTS && <span className="kuzram-facts-hint">Не больше {MAX_FACTS} строк.</span>}
      </div>
      {message && (
        <p className={`kuzram-message ${message.tone}`} role={message.tone === "error" ? "alert" : "status"}>
          {message.text}
        </p>
      )}
    </section>
  );
}
