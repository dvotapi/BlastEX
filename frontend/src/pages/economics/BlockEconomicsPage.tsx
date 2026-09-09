import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api } from "../../api/endpoints";
import { CostStructure } from "./CostStructure";
import { DrillingBreakdown } from "./DrillingBreakdown";
import { EconomicsHelp } from "./EconomicsHelp";
import { ModelWarnings } from "./ModelWarnings";
import { NomenclaturePanel } from "./NomenclaturePanel";
import { ParametersPanel } from "./ParametersPanel";
import { PassportStrip } from "./PassportStrip";
import { ServicesPanel } from "./ServicesPanel";
import { useWorkspace } from "../../app/useWorkspace";
import { PricePanel } from "./PricePanel";
import { RunsCompare } from "./RunsCompare";
import { SensitivityTable } from "./SensitivityTable";
import { VariantTabs } from "./VariantTabs";
import {
  duplicateVariant,
  makeVariant,
  patchVariant,
  removeVariant,
  renameVariant,
  type Variant,
} from "./variants";
import type {
  EconomicsRunSummary,
  ModelDefaults,
  ModelParameters,
  RunCompare,
  SensitivityRow,
  TechnicalPassport,
  VariantResult,
} from "../../types/blockEconomics";
import type { ReferenceRevision } from "../../types/economics";

const DEFAULT_PACKAGE = "DRILL_AND_BLAST";
const RECALC_DELAY_MS = 300;

export function BlockEconomicsPage({ passportId }: { passportId?: string | null }) {
  const [passports, setPassports] = useState<TechnicalPassport[]>([]);
  const [selectedPassport, setSelectedPassport] = useState(passportId ?? "");
  const [defaults, setDefaults] = useState<ModelDefaults | null>(null);
  // До четырёх колонок сметы: правит панели активный вариант, структура
  // затрат показывает все — один запрос на всех, чтобы колонки считались
  // на одной ревизии справочников (см. `POST .../variants` на бэкенде).
  //
  // Список вариантов и то, какой из них редактируется, — одно состояние, а
  // не два раздельных: добавление и удаление меняют оба сразу, и раздельные
  // setState гонятся друг с другом при двух кликах подряд в одном такте
  // React (второй читает список, ещё не увидевший первое изменение).
  const [variantsState, setVariantsState] = useState<{ variants: Variant[]; activeId: string }>({
    variants: [],
    activeId: "",
  });
  const { variants, activeId } = variantsState;
  const [results, setResults] = useState<VariantResult[]>([]);
  // Варианты, для которых считаны текущие `results` — по ним, а не по
  // индексу в массиве: список вариантов меняется сразу по клику, а ответ
  // сервера приходит позже, и без сверки по id вкладка «B» показала бы
  // цифры удалённого варианта «A», просто оказавшегося на его месте.
  const [resultsForIds, setResultsForIds] = useState<string[]>([]);
  const [runs, setRuns] = useState<EconomicsRunSummary[]>([]);
  const [selectedRuns, setSelectedRuns] = useState<string[]>([]);
  const [compare, setCompare] = useState<RunCompare | null>(null);
  const [sensitivity, setSensitivity] = useState<SensitivityRow[]>([]);
  const [runName, setRunName] = useState("");
  const [busy, setBusy] = useState(false);
  const [sensitivityBusy, setSensitivityBusy] = useState(false);
  const [error, setError] = useState("");
  const [status, setStatus] = useState("");
  const [movingService, setMovingService] = useState("");
  const { canEdit } = useWorkspace();
  // Подписи вместо кодов: имена объектов по ревизии паспорта и номера ревизий.
  const [siteNames, setSiteNames] = useState<Record<string, Record<string, string>>>({});
  const [revisions, setRevisions] = useState<ReferenceRevision[]>([]);
  const requestId = useRef(0);
  const defaultsRequestId = useRef(0);
  const sensitivityRequestId = useRef(0);
  // Чувствительность посчитана для этого варианта — переключение вкладки
  // само по себе не гонит новый расчёт, но и не должно показывать таблицу
  // соседнего варианта, пока сметчик не попросил пересчитать эту.
  const [sensitivityForId, setSensitivityForId] = useState("");

  useEffect(() => {
    api.economics
      .technicalPassports()
      .then((items) => {
        setPassports(items);
        setSelectedPassport((current) => current || items[0]?.id || "");
      })
      .catch((reason) =>
        setError(reason instanceof Error ? reason.message : "Не удалось загрузить паспорта."),
      );
    // Список ревизий нужен только для подписи; его отсутствие страницу не ломает.
    api.economics.revisions().then(setRevisions).catch(() => setRevisions([]));
  }, []);

  useEffect(() => {
    if (passportId) setSelectedPassport(passportId);
  }, [passportId]);

  // Паспорт сменился — начинаем заново с одного варианта на нормативном
  // пакете. Смену пакета у уже открытого варианта отслеживает эффект ниже:
  // она не должна стирать остальные колонки сравнения.
  const loadDefaults = useCallback(async () => {
    if (!selectedPassport) return;
    // Пользователь может переключить паспорт до ответа: результат устаревшего
    // запроса не должен подменить параметры уже выбранного паспорта.
    const id = ++defaultsRequestId.current;
    setBusy(true);
    setError("");
    try {
      const loaded = await api.blockEconomics.modelDefaults(selectedPassport, DEFAULT_PACKAGE);
      const saved = await api.blockEconomics.runs(selectedPassport);
      if (id !== defaultsRequestId.current) return;
      setDefaults(loaded);
      const variant = makeVariant("Вариант 1", loaded.parameters);
      setVariantsState({ variants: [variant], activeId: variant.id });
      setResults([]);
      setResultsForIds([]);
      setRuns(saved);
      setCompare(null);
      setSelectedRuns([]);
      setSensitivity([]);
      setSensitivityForId("");
    } catch (reason) {
      if (id !== defaultsRequestId.current) return;
      setError(reason instanceof Error ? reason.message : "Не удалось открыть модель.");
    } finally {
      if (id === defaultsRequestId.current) setBusy(false);
    }
  }, [selectedPassport]);

  useEffect(() => {
    void loadDefaults();
  }, [loadDefaults]);

  const activePackageCode = variants.find((variant) => variant.id === activeId)?.parameters.package_code;
  /**
   * Пакет работ сменили у уже открытого варианта — обновляем каталог
   * (станки, операции, номенклатуру) под него, но список вариантов не
   * трогаем. Раньше это делал `loadDefaults`, и смена пакета у одного
   * варианта тихо стирала остальные колонки сравнения.
   */
  useEffect(() => {
    if (!selectedPassport || !activePackageCode || !defaults) return;
    if (activePackageCode === defaults.parameters.package_code) return;
    let cancelled = false;
    api.blockEconomics
      .modelDefaults(selectedPassport, activePackageCode)
      .then((loaded) => {
        if (!cancelled) setDefaults(loaded);
      })
      .catch(() => {
        // Каталог для нового пакета не подгрузился — прежний остаётся
        // видимым и рабочим, останавливать редактирование варианта незачем.
      });
    return () => {
      cancelled = true;
    };
  }, [selectedPassport, activePackageCode, defaults]);

  // Пересчёт с задержкой: пользователь двигает параметры, а не жмёт «Рассчитать».
  // Один запрос на все варианты — так колонки остаются на одной ревизии
  // справочников, даже если правят не активный, а более раннюю вкладку.
  useEffect(() => {
    if (variants.length === 0 || !selectedPassport) return;
    const id = ++requestId.current;
    // На момент ответа список вариантов мог уже смениться (сметчик удалил
    // или дублировал вкладку) — запрос помнит, для кого он был отправлен.
    const requestedIds = variants.map((variant) => variant.id);
    const timer = window.setTimeout(() => {
      api.blockEconomics
        .variants(
          selectedPassport,
          variants.map((variant) => ({ name: variant.name, parameters: variant.parameters })),
        )
        .then((response) => {
          if (id === requestId.current) {
            setResults(response.variants);
            setResultsForIds(requestedIds);
            setError("");
          }
        })
        .catch((reason) => {
          if (id === requestId.current) {
            setError(reason instanceof Error ? reason.message : "Не удалось посчитать блок.");
          }
        });
    }, RECALC_DELAY_MS);
    return () => window.clearTimeout(timer);
  }, [variants, selectedPassport]);

  const activeVariant = variants.find((variant) => variant.id === activeId) ?? null;

  // Чувствительность посчитана для конкретного варианта, а не для вкладки
  // вообще: переключение (клик, дублирование, удаление активного) прячет
  // таблицу соседа вместо того, чтобы показывать её под чужим заголовком.
  // Счётчик запроса гасится тем же эффектом: ответ по варианту, с которого
  // уже ушли, не должен лечь в таблицу, даже если он ещё летит.
  useEffect(() => {
    if (activeId === sensitivityForId) return;
    setSensitivity([]);
    sensitivityRequestId.current += 1;
  }, [activeId, sensitivityForId]);

  // Совпадают состав и порядок id — тогда `results` точно про текущие
  // вкладки, а не про то, что было до последнего добавления/удаления.
  const resultsMatchVariants =
    resultsForIds.length === variants.length && resultsForIds.every((id, index) => id === variants[index]?.id);
  const activeResultIndex = resultsMatchVariants ? resultsForIds.indexOf(activeId) : -1;
  const activeEconomics = activeResultIndex >= 0 ? results[activeResultIndex]?.economics ?? null : null;

  const passport = useMemo(
    () => defaults?.passport ?? passports.find((item) => item.id === selectedPassport) ?? null,
    [defaults, passports, selectedPassport],
  );

  // Имя объекта берётся из той ревизии, на которой создан паспорт: объект
  // могли переименовать позже, а паспорт фиксирует состояние на момент выпуска.
  const revisionId = passport?.reference_revision_id ?? "";
  useEffect(() => {
    if (!revisionId || siteNames[revisionId]) return;
    api.economics
      .referenceSnapshot(revisionId)
      .then((snapshot) => {
        const names: Record<string, string> = {};
        for (const item of snapshot.sections.sites ?? []) names[item.code] = item.name;
        setSiteNames((current) => ({ ...current, [revisionId]: names }));
      })
      .catch(() => setSiteNames((current) => ({ ...current, [revisionId]: {} })));
  }, [revisionId, siteNames]);

  const siteLabel = passport
    ? siteNames[revisionId]?.[passport.site_code] ?? passport.site_code
    : "";
  const revisionLabel = useMemo(() => {
    if (!revisionId) return "";
    const found = revisions.find((item) => item.id === revisionId);
    if (!found) return revisionId;
    const date = new Date(found.published_at).toLocaleDateString("ru-RU");
    return `Ревизия ${found.sequence_no} от ${date}`;
  }, [revisionId, revisions]);

  /** Услуга уходит в правила затрат новой ревизией и исчезает из параметров активного варианта: иначе двойной счёт. */
  async function moveServiceToReference(index: number) {
    const service = activeVariant?.parameters.services[index];
    if (!service || !activeId) return;
    setMovingService(service.name);
    setError("");
    try {
      const moved = await api.blockEconomics.serviceToReference(service);
      // Из текущего состояния, а не из захваченного activeVariant: пока шла
      // публикация ревизии, сметчик мог править ту же вкладку ещё раз.
      setVariantsState((current) => ({
        ...current,
        variants: current.variants.map((variant) =>
          variant.id === activeId
            ? {
                ...variant,
                parameters: {
                  ...variant.parameters,
                  services: variant.parameters.services.filter((item) => item !== service),
                },
              }
            : variant,
        ),
      }));
      setStatus(
        `«${service.name}» ${moved.created ? "добавлена" : "обновлена"} в правилах затрат как ${moved.code}.`,
      );
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Не удалось перенести услугу в справочник.");
    } finally {
      setMovingService("");
    }
  }

  function patchActive(patch: Partial<ModelParameters>) {
    setVariantsState((current) =>
      current.activeId
        ? { ...current, variants: patchVariant(current.variants, current.activeId, patch) }
        : current,
    );
  }

  function selectVariant(id: string) {
    setVariantsState((current) => ({ ...current, activeId: id }));
  }

  /**
   * Копия активного варианта становится активной: сравнивают её с исходным,
   * меняя одно поле. Список и активный id меняются одним `setState`, а не
   * двумя — иначе два быстрых клика подряд читают один и тот же список,
   * ещё не увидевший первое изменение, и одно из двух действий теряется.
   */
  function handleDuplicateVariant() {
    setVariantsState((current) => {
      if (!current.activeId) return current;
      const next = duplicateVariant(current.variants, current.activeId);
      if (next === current.variants) return current;
      return { variants: next, activeId: next[next.length - 1].id };
    });
  }

  function handleRemoveVariant(id: string) {
    setVariantsState((current) => {
      const next = removeVariant(current.variants, id);
      if (next === current.variants) return current;
      return {
        variants: next,
        activeId: id === current.activeId ? next[0]?.id ?? "" : current.activeId,
      };
    });
  }

  function handleRenameVariant(id: string, name: string) {
    setVariantsState((current) => ({ ...current, variants: renameVariant(current.variants, id, name) }));
  }

  async function saveRun() {
    if (!activeVariant || !selectedPassport) return;
    const name = runName.trim() || `Сценарий ${runs.length + 1}`;
    setBusy(true);
    try {
      await api.blockEconomics.saveRun(selectedPassport, activeVariant.parameters, name);
      setRuns(await api.blockEconomics.runs(selectedPassport));
      setRunName("");
      setStatus(`Сценарий «${name}» сохранён.`);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Не удалось сохранить сценарий.");
    } finally {
      setBusy(false);
    }
  }

  async function computeSensitivity() {
    if (!activeVariant || !selectedPassport) return;
    const id = ++sensitivityRequestId.current;
    // Пока считаем, сметчик мог переключить вкладку: ответ по старому
    // варианту не должен лечь в таблицу под новым активным заголовком.
    const forId = activeVariant.id;
    setSensitivityBusy(true);
    try {
      const response = await api.blockEconomics.sensitivity(selectedPassport, activeVariant.parameters);
      if (id !== sensitivityRequestId.current) return;
      setSensitivity(response.rows);
      setSensitivityForId(forId);
    } catch (reason) {
      if (id !== sensitivityRequestId.current) return;
      setError(reason instanceof Error ? reason.message : "Не удалось посчитать чувствительность.");
    } finally {
      if (id === sensitivityRequestId.current) setSensitivityBusy(false);
    }
  }

  async function compareRuns() {
    if (selectedRuns.length < 2) return;
    setBusy(true);
    try {
      setCompare(await api.blockEconomics.compare(selectedRuns));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Не удалось сравнить сценарии.");
    } finally {
      setBusy(false);
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
      <PassportStrip
        passports={passports}
        selectedId={selectedPassport}
        onSelect={setSelectedPassport}
        passport={passport}
        siteLabel={siteLabel}
        revisionLabel={revisionLabel}
        runName={runName}
        runPlaceholder={`Сценарий ${runs.length + 1}`}
        onRunName={setRunName}
        onSave={() => void saveRun()}
        saveDisabled={busy || !activeEconomics}
        status={status}
      />
      <div className="page-content block-economics-content">
        <EconomicsHelp />
        {error && <div className="page-error" role="alert">{error}</div>}

        <div className="block-economics-grid">
          {defaults && activeVariant && (
            <div className="block-economics-inputs">
              <VariantTabs
                variants={variants}
                activeId={activeId}
                onSelect={selectVariant}
                onDuplicate={handleDuplicateVariant}
                onRemove={handleRemoveVariant}
                onRename={handleRenameVariant}
              />
              <NomenclaturePanel params={activeVariant.parameters} defaults={defaults} onChange={patchActive} />
              <ParametersPanel
                params={activeVariant.parameters}
                defaults={defaults}
                computedRevisionId={activeEconomics?.reference_revision_id}
                onChange={patchActive}
              />
              <ServicesPanel
                services={activeVariant.parameters.services}
                operations={defaults.operations}
                canEdit={canEdit}
                busyCode={movingService}
                onChange={(services) => patchActive({ services })}
                onMove={(index) => void moveServiceToReference(index)}
              />
            </div>
          )}
          <div className="block-economics-results">
            {results.length > 0 && activeEconomics ? (
              <>
                <PricePanel economics={activeEconomics} />
                <ModelWarnings economics={activeEconomics} />
                <DrillingBreakdown economics={activeEconomics} />
                <CostStructure results={results} />
              </>
            ) : (
              <div className="economic-empty">Расчёт выполняется…</div>
            )}
          </div>
        </div>

        <SensitivityTable rows={sensitivity} busy={sensitivityBusy} onCompute={() => void computeSensitivity()} />

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
      </div>
    </div>
  );
}
