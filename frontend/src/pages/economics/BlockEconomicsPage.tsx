import { useEffect, useRef, useState, type ReactNode } from "react";
import { useWorkspace } from "../../app/useWorkspace";
import { CostStructure } from "./CostStructure";
import { EconomicsHeader } from "./EconomicsHeader";
import { EconomicsErrorBoundary } from "./EconomicsErrorBoundary";
import { EconomicsHelp } from "./EconomicsHelp";
import { EconomicsTabs, type EconomicsTab } from "./EconomicsTabs";
import { HistoryTab } from "./HistoryTab";
import { PassportStrip } from "./PassportStrip";
import { TopbarSelectors } from "./TopbarSelectors";
import { ResourcesTab } from "./ResourcesTab";
import { RunsCompare } from "./RunsCompare";
import { SensitivityTable } from "./SensitivityTable";
import { VariantTabs } from "./VariantTabs";
import { EstimateBuilder } from "./estimate/EstimateBuilder";
import { ESTIMATE_GROUPS, type EstimateGroup, type EstimateGroupCode } from "./estimateModel";
import { DrillingSection } from "./sections/DrillingSection";
import { EquipmentSection } from "./sections/EquipmentSection";
import { ExplosivesSection } from "./sections/ExplosivesSection";
import { FixedCostsSection } from "./sections/FixedCostsSection";
import { FuelSection } from "./sections/FuelSection";
import { LaborSection } from "./sections/LaborSection";
import { ServicesSection } from "./sections/ServicesSection";
import { EconomicsSidebar } from "./sidebar/EconomicsSidebar";
import { BlockEconomicsSessionProvider, useBlockEconomicsSessionContext, useOptionalBlockEconomicsSession } from "./BlockEconomicsSessionContext";
import type { ModelParameters } from "../../types/blockEconomics";

/** Сколько раздел сметы остаётся подсвеченным после клика по сегменту диаграммы. */
const HIGHLIGHT_DURATION_MS = 1500;
/** Ключ `sessionStorage`, под которым запоминаются раскрытые разделы сметы. */
const EXPANDED_STORAGE_KEY = "blastex.economics.expanded";

/**
 * Раскрытые разделы читаются из `sessionStorage` один раз при инициализации
 * страницы — приватный режим браузера может запретить доступ к хранилищу,
 * поэтому чтение обёрнуто в `try/catch` и при любой ошибке (или отсутствии
 * записи) просто возвращает пустой набор.
 */
function readExpandedFromStorage(): Set<EstimateGroupCode> {
  try {
    const raw = window.sessionStorage.getItem(EXPANDED_STORAGE_KEY);
    if (!raw) return new Set();
    const parsed: unknown = JSON.parse(raw);
    if (!Array.isArray(parsed)) return new Set();
    const codes = new Set(ESTIMATE_GROUPS.map((group) => group.code));
    return new Set(parsed.filter((code): code is EstimateGroupCode => codes.has(code)));
  } catch {
    return new Set();
  }
}

/** Запись тоже обёрнута в `try/catch` — по той же причине, что и чтение. */
function writeExpandedToStorage(expanded: Set<EstimateGroupCode>) {
  try {
    window.sessionStorage.setItem(EXPANDED_STORAGE_KEY, JSON.stringify(Array.from(expanded)));
  } catch {
    // Хранилище недоступно (приватный режим и т.п.) — раскрытые разделы просто не запоминаются.
  }
}

type PageProps = {
  passportId?: string | null;
  /** Открыть страницу «Бурение». */
  onOpenDrilling: () => void;
};

/**
 * Над страницей обычно стоит общий провайдер расчёта блока (его ставит
 * `AppShell`, чтобы черновики переживали переход на «Бурение»). Без него
 * страница заводит собственную сессию — так она работает отдельно, например в тестах.
 */
export function BlockEconomicsPage(props: PageProps) {
  const shared = useOptionalBlockEconomicsSession();
  if (shared) return <BlockEconomicsPageBody {...props} />;
  return (
    <BlockEconomicsSessionProvider passportId={props.passportId}>
      <BlockEconomicsPageBody {...props} />
    </BlockEconomicsSessionProvider>
  );
}

function BlockEconomicsPageBody({ onOpenDrilling }: PageProps) {
  const {
    passports, selectedPassport, setSelectedPassport, defaults, drafts, activeId, activeDraft, dirty,
    results, runs, selectedRuns, setSelectedRuns, compare, sensitivity, busy, sensitivityBusy, error,
    status, movingService, resultsMatchDrafts, activeEconomics, volume, groups, passport, siteLabel,
    revisionLabel, passportRevisionLabel, passportContextLabel, exportUrl, reloadDefaults, patchDraft,
    selectDraft, duplicateActive, resetActiveDraft, removeDraft, renameDraft, moveServiceToReference,
    saveActive, openRun, computeSensitivity, compareRuns,
  } = useBlockEconomicsSessionContext();
  const [tab, setTab] = useState<EconomicsTab>("estimate");
  const [expanded, setExpanded] = useState<Set<EstimateGroupCode>>(() => readExpandedFromStorage());
  const [highlighted, setHighlighted] = useState<EstimateGroupCode | null>(null);
  const [donutUnit, setDonutUnit] = useState<"₽" | "₽/м³">("₽/м³");
  const { canEdit } = useWorkspace();
  const highlightTimer = useRef<number | undefined>(undefined);

  useEffect(() => () => window.clearTimeout(highlightTimer.current), []);

  // Раскрытые разделы переживают перезагрузку вкладки в пределах вкладки
  // браузера: запоминаем набор при каждом изменении.
  useEffect(() => {
    writeExpandedToStorage(expanded);
  }, [expanded]);

  function toggleGroup(code: EstimateGroupCode) {
    setExpanded((current) => {
      const next = new Set(current);
      if (next.has(code)) next.delete(code);
      else next.add(code);
      return next;
    });
  }

  function expandAll() {
    setExpanded(new Set(ESTIMATE_GROUPS.map((item) => item.code)));
  }

  function collapseAll() {
    setExpanded(new Set());
  }

  /** Клик по сегменту диаграммы: раскрывает раздел на вкладке «Смета», прокручивает к нему и на 1,5 с подсвечивает. */
  function selectGroupFromChart(code: EstimateGroupCode) {
    setTab("estimate");
    setExpanded((current) => (current.has(code) ? current : new Set(current).add(code)));
    setHighlighted(code);
    window.clearTimeout(highlightTimer.current);
    highlightTimer.current = window.setTimeout(() => setHighlighted(null), HIGHLIGHT_DURATION_MS);
    window.requestAnimationFrame(() => {
      document.getElementById(`estimate-section-${code}`)?.scrollIntoView({ behavior: "smooth", block: "start" });
    });
  }

  function renderEstimateGroup(group: EstimateGroup): ReactNode {
    if (!defaults || !activeDraft) return null;
    const common = {
      group,
      params: activeDraft.parameters,
      defaults,
      economics: activeEconomics,
      volume,
      canEdit,
      onChange: (patch: Partial<ModelParameters>) => patchDraft(activeDraft.id, patch),
    };
    switch (group.code) {
      case "EXPLOSIVES":
        return <ExplosivesSection {...common} />;
      case "DRILLING":
        return <DrillingSection {...common} onOpenDrillingPage={onOpenDrilling} onDefaultsChanged={() => void reloadDefaults()} />;
      case "LABOR":
        return <LaborSection {...common} />;
      case "EQUIPMENT":
        return <EquipmentSection {...common} onOpenDrillingGroup={() => selectGroupFromChart("DRILLING")} />;
      case "FUEL":
        return <FuelSection {...common} />;
      case "SERVICES":
        return (
          <ServicesSection
            {...common}
            busyServiceName={movingService}
            onMoveService={(index) => void moveServiceToReference(index)}
          />
        );
      case "FIXED":
        return <FixedCostsSection {...common} />;
      default:
        return null;
    }
  }

  if (!selectedPassport) {
    return (
      <div className="page-content">
        <h2>Экономика блока</h2>
        {error && <div className="page-error">{error}</div>}
        <p className="page-caption">
          Сохранённых технических паспортов нет. Сохраните паспорт на вкладке «Расчёт БВР» —
          экономика считается по нему.
        </p>
      </div>
    );
  }

  return (
    <div className="block-economics-page">
      <EconomicsHelp />
      <TopbarSelectors
        passports={passports}
        selectedId={selectedPassport}
        onSelect={setSelectedPassport}
        siteLabel={siteLabel}
        siteTitle={passport?.site_code}
        revisionLabel={passportRevisionLabel}
        revisionTitle={passport?.reference_revision_id}
      />
      <EconomicsHeader
        context={{ site: siteLabel, passport: passportContextLabel, revision: revisionLabel }}
        drafts={drafts}
        runs={runs}
        activeId={activeId}
        onSelectDraft={selectDraft}
        onOpenRun={(runId) => void openRun(runId)}
        dirty={dirty}
        onSave={(name) => void saveActive(name)}
        onDuplicate={duplicateActive}
        onRename={(name) => renameDraft(activeId, name)}
        onRemove={() => removeDraft(activeId)}
        canRemove={drafts.length > 1}
        exportUrl={exportUrl}
        busy={busy}
        status={status}
        error=""
      />
      <PassportStrip passport={passport} />
      <div className="page-content block-economics-content">
        {error && (
          <div className="page-error" role="alert">
            {error}
          </div>
        )}

        {/* Ограничитель пересоздаётся вместе со сценарием: выбор другого
            сценария в шапке — рабочий путь из упавшего состояния, а сама шапка
            остаётся живой, потому что стоит выше ограничителя. */}
        <EconomicsErrorBoundary key={activeId} onReset={resetActiveDraft}>
        <div className="economics-workspace">
          <div className="economics-main">
            <div className="economics-card">
            <EconomicsTabs active={tab} onChange={setTab} />

            {tab === "estimate" &&
              (activeEconomics ? (
                // Без обёртки с прокруткой: любой предок с `overflow` делается
                // точкой отсчёта для липкой шапки колонок, и та застывает
                // внутри таблицы вместо верха окна.
                <>
                {/* Предупреждения модели — над сметой, а не только на вкладке
                    «Ресурсы»: нулевая строка бурения или неразнесённые
                    постоянные затраты видны там, где на них смотрят. */}
                {activeEconomics.warnings.length > 0 && (
                  <details className="estimate-warnings">
                    <summary>
                      Модель сообщает: {activeEconomics.warnings.length}
                    </summary>
                    <ul>
                      {activeEconomics.warnings.map((warning) => (
                        <li key={warning}>{warning}</li>
                      ))}
                    </ul>
                  </details>
                )}
                <div className="estimate-scroll">
                  <EstimateBuilder
                    // Смена черновика (`activeId`) должна сбрасывать весь
                    // локальный стейт разделов сметы одним движением — например,
                    // выбор подрядчика в `SubcontractDrillingEditor`, который
                    // иначе «протекает» между черновиками с разными (или без)
                    // выбранными тарифами. `key` пересоздаёт поддерево целиком;
                    // раскрытые разделы (`expanded`) не пострадают — они живут
                    // здесь, на уровне страницы, а не внутри `EstimateBuilder`.
                    key={activeId}
                    groups={groups}
                    volume={volume}
                    expanded={expanded}
                    onToggle={toggleGroup}
                    onExpandAll={expandAll}
                    onCollapseAll={collapseAll}
                    highlighted={highlighted}
                    renderGroup={renderEstimateGroup}
                    busy={!resultsMatchDrafts}
                  />
                </div>
                </>
              ) : (
                <div className="economic-empty">Расчёт выполняется…</div>
              ))}

            {tab === "structure" && (
              <>
                <VariantTabs
                  variants={drafts}
                  activeId={activeId}
                  onSelect={selectDraft}
                  onDuplicate={duplicateActive}
                  onRemove={removeDraft}
                  onRename={renameDraft}
                />
                <CostStructure results={results} />
              </>
            )}

            {tab === "resources" &&
              (activeEconomics ? (
                <ResourcesTab economics={activeEconomics} />
              ) : (
                <div className="economic-empty">Расчёт выполняется…</div>
              ))}

            {tab === "sensitivity" && (
              <SensitivityTable rows={sensitivity} busy={sensitivityBusy} onCompute={() => void computeSensitivity()} />
            )}

            {tab === "compare" && (
              <RunsCompare
                runs={runs}
                selected={selectedRuns}
                compare={compare}
                busy={busy}
                onToggle={(runId) =>
                  setSelectedRuns((current) =>
                    current.includes(runId)
                      ? current.filter((item) => item !== runId)
                      : current.length >= 3
                        ? current
                        : [...current, runId],
                  )
                }
                onCompare={() => void compareRuns()}
              />
            )}

            {tab === "history" && <HistoryTab runs={runs} onOpen={(runId) => void openRun(runId)} />}
            </div>
          </div>

          {activeEconomics && (
            <EconomicsSidebar
              economics={activeEconomics}
              groups={groups}
              unit={donutUnit}
              onUnitChange={setDonutUnit}
              highlighted={highlighted}
              onSelect={selectGroupFromChart}
            />
          )}
        </div>
        </EconomicsErrorBoundary>
      </div>
    </div>
  );
}
