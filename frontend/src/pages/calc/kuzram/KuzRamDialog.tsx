import { useEffect, useId, useRef, useState, type KeyboardEvent, type MouseEvent } from "react";
import type { BlastVariant, KuzRamCalibrateResponse, KuzRamFactInput, KuzRamSettings } from "../../../types";
import { KuzRamBreakdown } from "./KuzRamBreakdown";
import { KuzRamChart } from "./KuzRamChart";
import { KuzRamComparison } from "./KuzRamComparison";
import { KuzRamFacts } from "./KuzRamFacts";
import { KuzRamHelp } from "./KuzRamHelp";
import { KuzRamSettingsForm } from "./KuzRamSettingsForm";
import { trimmed } from "./kuzramFormat";
import { completeFacts, kuzramSettingsOf, type KuzRamBlock, type KuzRamFact } from "./kuzramSettings";

/** Исходные данные листа — в окне только строкой, правятся на листе. */
export type KuzRamSource = {
  rockName: string;
  explosiveName: string;
  benchHeightM: number;
  overdrillM: number;
  lumpSizeMm: number;
  thresholdPct: number;
  /** Выбранные коронки — из чекбоксов листа. */
  crownsMm: number[];
};

const TAB_NAMES = ["calc", "help"] as const;
type TabName = (typeof TAB_NAMES)[number];

export type KuzRamDialogProps = {
  open: boolean;
  onClose: () => void;
  /** Блок модели объекта: настройки и фактические взрывы. */
  block: KuzRamBlock;
  /** Правка настроек: лист сохраняет их и пересчитывает варианты. */
  onSettingsChange: (next: KuzRamSettings) => void;
  source: KuzRamSource;
  /** Идёт подбор q (или пауза перед ним после правки) — прежние цифры приглушены. */
  busy: boolean;
  /** Ошибка последнего подбора — та же, что на листе. */
  error: string;
  /** Варианты последнего подбора: Kuz-Ram, «до исправления» и разбор. */
  variants: BlastVariant[];
  /** Выбранная коронка — общая с таблицей листа. */
  selectedIndex: number;
  onSelect: (index: number) => void;
  /** Порог негабарита, с которым посчитаны варианты. */
  thresholdPct: number;
  /** Правка строк фактов: лист сохраняет их, подбор q не запускается. */
  onFactsChange: (next: KuzRamFact[]) => void;
  /** Подбор C(A) по полным строкам — запрос `/blast/kuzram/calibrate` с данными листа. */
  onCalibrate: (facts: KuzRamFactInput[]) => Promise<KuzRamCalibrateResponse>;
};

/**
 * Окно «Модель Kuz-Ram» листа «Расчёт». Нативный `dialog` с `showModal()`,
 * как у `CalcHelp`: Esc и щелчок по подложке закрывают окно. Всё считает
 * сервер: окно показывает ответ `/blast/optimize` и отдаёт правки листу.
 * Содержимое рисуется только у открытого окна — при каждом открытии поля
 * заново берут сохранённые значения.
 */
export function KuzRamDialog(props: KuzRamDialogProps) {
  const { open, onClose } = props;
  const ref = useRef<HTMLDialogElement>(null);
  const [tab, setTab] = useState<TabName>("calc");
  const ids = useId();
  const tabId = (name: TabName) => `${ids}-tab-${name}`;
  const panelId = (name: TabName) => `${ids}-panel-${name}`;
  // Фокус переключателя вкладок стрелками — переносим его на новую кнопку.
  const tabButtonRefs = useRef<Record<TabName, HTMLButtonElement | null>>({ calc: null, help: null });

  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    if (open && !dialog.open) dialog.showModal();
    if (!open && dialog.open) dialog.close();
  }, [open]);

  // Щелчок по подложке приходит в сам `dialog`, по содержимому — во вложенные элементы.
  function onBackdropClick(event: MouseEvent<HTMLDialogElement>) {
    if (event.target === ref.current) onClose();
  }

  // Стандартный ARIA-паттерн вкладок: стрелки переключают вкладку и фокус на
  // ней же (у окна их только две, поэтому обе стрелки просто меняют вкладку).
  function onTabKeyDown(event: KeyboardEvent<HTMLButtonElement>, name: TabName) {
    if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
    event.preventDefault();
    const next = TAB_NAMES[(TAB_NAMES.indexOf(name) + 1) % TAB_NAMES.length];
    setTab(next);
    tabButtonRefs.current[next]?.focus();
  }

  return (
    <dialog
      ref={ref}
      className="kuzram-dialog"
      aria-labelledby="kuzram-dialog-title"
      onClose={onClose}
      onClick={onBackdropClick}
    >
      <header>
        <b id="kuzram-dialog-title">Модель Kuz-Ram</b>
        <div className="kuzram-tabs" role="tablist" aria-label="Разделы окна">
          {TAB_NAMES.map((name) => (
            <button
              key={name}
              ref={(el) => { tabButtonRefs.current[name] = el; }}
              type="button"
              role="tab"
              id={tabId(name)}
              aria-controls={panelId(name)}
              aria-selected={tab === name}
              onClick={() => setTab(name)}
              onKeyDown={(event) => onTabKeyDown(event, name)}
            >
              {name === "calc" ? "Расчёт" : "Как пользоваться"}
            </button>
          ))}
        </div>
        <button type="button" className="kuzram-close" aria-label="Закрыть" onClick={onClose}>
          ×
        </button>
      </header>
      {/* Обе панели рисуются, пока окно открыто, — переключение вкладок только
          скрывает неактивную атрибутом `hidden`, не размонтируя её: подбор
          C(A) или пересчёт, начатые на вкладке «Расчёт», не должны прерваться
          переходом на «Как пользоваться» и обратно. Всё окно всё равно не
          рисуется закрытым (`open &&`) — при следующем открытии поля заново
          берут сохранённые значения. */}
      {open && (
        <>
          <div
            role="tabpanel"
            id={panelId("calc")}
            aria-labelledby={tabId("calc")}
            className="kuzram-body kuzram-calc"
            hidden={tab !== "calc"}
          >
            <CalcTab {...props} />
          </div>
          <div role="tabpanel" id={panelId("help")} aria-labelledby={tabId("help")} className="kuzram-body" hidden={tab !== "help"}>
            <KuzRamHelp />
          </div>
        </>
      )}
    </dialog>
  );
}

function CalcTab({
  block,
  onSettingsChange,
  source,
  busy,
  error,
  variants,
  selectedIndex,
  onSelect,
  thresholdPct,
  onFactsChange,
  onCalibrate,
}: KuzRamDialogProps) {
  const chartFacts = completeFacts(block.facts).map((row) => row.fact);
  const selected = variants[selectedIndex];
  return (
    <>
      <aside className="kuzram-side">
        <KuzRamSettingsForm settings={block} onChange={onSettingsChange} />
        <p className="kuzram-source">
          <b>С листа:</b> {source.rockName} · {source.explosiveName} · уступ {trimmed(source.benchHeightM)} м, перебур{" "}
          {trimmed(source.overdrillM)} м · кусок {trimmed(source.lumpSizeMm)} мм · коронки{" "}
          {source.crownsMm.length > 0 ? `${source.crownsMm.map((mm) => trimmed(mm)).join(", ")} мм` : "не выбраны"} · допустимый негабарит{" "}
          {trimmed(source.thresholdPct)} %. Исходные данные меняются на листе.
        </p>
      </aside>
      <div className={`kuzram-results${busy ? " is-pending" : ""}`} aria-busy={busy}>
        <p className="kuzram-status" role="status">
          {busy ? "Пересчёт…" : ""}
        </p>
        {error && (
          <div className="page-error" role="alert">
            {error}
          </div>
        )}
        <KuzRamComparison variants={variants} selectedIndex={selectedIndex} onSelect={onSelect} thresholdPct={thresholdPct} />
        {variants.length > 0 && (
          <section className="kuzram-card" aria-labelledby="kuzram-chart-title">
            <h3 id="kuzram-chart-title">Удельный расход по диаметрам коронок</h3>
            <KuzRamChart variants={variants} facts={chartFacts} selectedIndex={selectedIndex} onSelect={onSelect} />
          </section>
        )}
        {selected && <KuzRamBreakdown variant={selected} thresholdPct={thresholdPct} />}
        <KuzRamFacts
          facts={block.facts}
          onChange={onFactsChange}
          defaultCrownMm={selected?.crown_mm ?? null}
          onCalibrate={onCalibrate}
          onApplyCorrection={(value) => {
            // Настройки не изменились с подбора (частый случай — повторный
            // подбор на тех же данных) — не гоняем пересчёт варианта впустую.
            if (value === block.rock_factor_correction) return;
            onSettingsChange({ ...kuzramSettingsOf(block), rock_factor_correction: value });
          }}
        />
      </div>
    </>
  );
}
