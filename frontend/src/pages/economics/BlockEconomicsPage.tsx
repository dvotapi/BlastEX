import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { api } from "../../api/endpoints";
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
import { buildEstimate, ESTIMATE_GROUPS, type EstimateGroup, type EstimateGroupCode } from "./estimateModel";
import { DrillingSection } from "./sections/DrillingSection";
import { EquipmentSection } from "./sections/EquipmentSection";
import { ExplosivesSection } from "./sections/ExplosivesSection";
import { FixedCostsSection } from "./sections/FixedCostsSection";
import { FuelSection } from "./sections/FuelSection";
import { LaborSection } from "./sections/LaborSection";
import { ServicesSection } from "./sections/ServicesSection";
import { draftFromDefaults, draftFromRun, isDirty, markSavedIfCurrent, type Draft } from "./scenario";
import { EconomicsSidebar } from "./sidebar/EconomicsSidebar";
import { MAX_VARIANTS } from "./variants";
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

/**
 * Человекочитаемая подпись ревизии справочников по её id: «Ревизия N от
 * ДД.ММ.ГГГГ», либо сам id, если ревизия ещё не подгружена в `revisions`.
 * Используется и для ревизии расчёта (шапка сценариев), и для ревизии
 * паспорта (полоса паспорта) — это разные id, которые могут расходиться.
 */
function formatRevisionLabel(revisionId: string, revisions: ReferenceRevision[]): string {
  if (!revisionId) return "";
  const found = revisions.find((item) => item.id === revisionId);
  if (!found) return revisionId;
  const date = new Date(found.published_at).toLocaleDateString("ru-RU");
  return `Ревизия ${found.sequence_no} от ${date}`;
}

export function BlockEconomicsPage({
  passportId,
  onOpenDrilling,
}: {
  passportId?: string | null;
  /** Открыть отдельный калькулятор бурения (вкладка «Бурение», Cost V1). */
  onOpenDrilling: () => void;
}) {
  const [passports, setPassports] = useState<TechnicalPassport[]>([]);
  const [selectedPassport, setSelectedPassport] = useState(passportId ?? "");
  const [defaults, setDefaults] = useState<ModelDefaults | null>(null);
  // Сценарии вкладки — до четырёх черновиков, редактируемых параллельно, и
  // то, какой из них открыт сейчас. Список и активный id меняются одним
  // `setState`, а не двумя раздельных: иначе два быстрых клика подряд читают
  // один и тот же список, ещё не увидевший первое изменение.
  const [draftsState, setDraftsState] = useState<{ drafts: Draft[]; activeId: string }>({
    drafts: [],
    activeId: "",
  });
  const { drafts, activeId } = draftsState;
  const [results, setResults] = useState<VariantResult[]>([]);
  // Черновики, для которых считаны текущие `results` — по id, а не по
  // индексу: список черновиков меняется сразу по клику, а ответ сервера
  // приходит позже, и без сверки по id вкладка «B» показала бы цифры
  // удалённого черновика «A», просто оказавшегося на его месте.
  const [resultsForIds, setResultsForIds] = useState<string[]>([]);
  const [runs, setRuns] = useState<EconomicsRunSummary[]>([]);
  const [selectedRuns, setSelectedRuns] = useState<string[]>([]);
  const [compare, setCompare] = useState<RunCompare | null>(null);
  const [sensitivity, setSensitivity] = useState<SensitivityRow[]>([]);
  const [busy, setBusy] = useState(false);
  const [sensitivityBusy, setSensitivityBusy] = useState(false);
  const [error, setError] = useState("");
  const [status, setStatus] = useState("");
  const [movingService, setMovingService] = useState("");
  const [tab, setTab] = useState<EconomicsTab>("estimate");
  const [expanded, setExpanded] = useState<Set<EstimateGroupCode>>(() => readExpandedFromStorage());
  const [highlighted, setHighlighted] = useState<EstimateGroupCode | null>(null);
  const [donutUnit, setDonutUnit] = useState<"₽" | "₽/м³">("₽/м³");
  const { canEdit } = useWorkspace();
  // Подписи вместо кодов: имена объектов по ревизии паспорта и номера ревизий.
  const [siteNames, setSiteNames] = useState<Record<string, Record<string, string>>>({});
  const [revisions, setRevisions] = useState<ReferenceRevision[]>([]);
  const requestId = useRef(0);
  const defaultsRequestId = useRef(0);
  const sensitivityRequestId = useRef(0);
  const highlightTimer = useRef<number | undefined>(undefined);
  // Чувствительность посчитана для этого черновика — переключение вкладки
  // само по себе не гонит новый расчёт, но и не должно показывать таблицу
  // соседнего черновика, пока сметчик не попросил пересчитать эту.
  const [sensitivityForId, setSensitivityForId] = useState("");
  // Живое зеркало `selectedPassport` для сверки ПОСЛЕ `await` в `openRun`:
  // сравнение двух чтений обычной переменной состояния внутри одного и того
  // же замыкания асинхронной функции всегда даёт равенство (замыкание не
  // видит более поздних рендеров) — нужен `ref`, как и для `requestId` выше.
  const selectedPassportRef = useRef(selectedPassport);
  useEffect(() => {
    selectedPassportRef.current = selectedPassport;
  }, [selectedPassport]);
  // То же зеркало для каталога умолчаний: `openRun` читает его уже после
  // `await`, чтобы дополнить параметры старого прогона недостающими полями.
  const defaultsRef = useRef(defaults);
  useEffect(() => {
    defaultsRef.current = defaults;
  }, [defaults]);

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

  useEffect(() => () => window.clearTimeout(highlightTimer.current), []);

  // Раскрытые разделы переживают перезагрузку вкладки в пределах вкладки
  // браузера: запоминаем набор при каждом изменении.
  useEffect(() => {
    writeExpandedToStorage(expanded);
  }, [expanded]);

  // Паспорт сменился — начинаем заново с одного черновика на нормативном
  // пакете. Смену пакета у уже открытого черновика отслеживает эффект ниже:
  // она не должна стирать остальные вкладки сравнения.
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
      const draft = draftFromDefaults("Вариант 1", loaded.parameters);
      setDraftsState({ drafts: [draft], activeId: draft.id });
      setResults([]);
      setResultsForIds([]);
      setRuns(saved);
      setCompare(null);
      setSelectedRuns([]);
      setSensitivity([]);
      setSensitivityForId("");
      setStatus("");
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

  const activePackageCode = drafts.find((draft) => draft.id === activeId)?.parameters.package_code;

  /**
   * Каталог (`defaults`) обновляется без сброса черновиков — в отличие от
   * `loadDefaults`, который начинает вкладку заново. Нужен после публикации
   * записи в справочник прямо со сметы (например, тариф субподряда бурения,
   * `SubcontractDrillingEditor`): опубликованный код должен появиться в
   * `defaults.subcontract_rates` сразу, иначе выбор тарифа, только что
   * записанный в параметры черновика, не находится в старом снимке каталога
   * и выглядит так, будто сбросился.
   */
  const reloadDefaults = useCallback(async () => {
    if (!selectedPassport || !activePackageCode) return;
    try {
      const loaded = await api.blockEconomics.modelDefaults(selectedPassport, activePackageCode);
      setDefaults(loaded);
    } catch {
      // Прежний каталог остаётся видимым и рабочим — обновление не критично
      // для продолжения работы с уже выбранным тарифом.
    }
  }, [selectedPassport, activePackageCode]);

  /**
   * Пакет работ сменили у уже открытого черновика — обновляем каталог
   * (станки, операции, номенклатуру) под него, но список черновиков не
   * трогаем. Раньше это делал `loadDefaults`, и смена пакета у одного
   * черновика тихо стирала остальные вкладки сравнения.
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
        // видимым и рабочим, останавливать редактирование черновика незачем.
      });
    return () => {
      cancelled = true;
    };
  }, [selectedPassport, activePackageCode, defaults]);

  // Пересчёт с задержкой: сметчик двигает параметры, а не жмёт «Рассчитать».
  // Один запрос на все черновики — так вкладки остаются на одной ревизии
  // справочников, даже если правят не активный, а более раннюю вкладку.
  useEffect(() => {
    if (drafts.length === 0 || !selectedPassport) return;
    const id = ++requestId.current;
    // На момент ответа список черновиков мог уже смениться (сметчик удалил
    // или дублировал вкладку) — запрос помнит, для кого он был отправлен.
    const requestedIds = drafts.map((draft) => draft.id);
    const timer = window.setTimeout(() => {
      api.blockEconomics
        .variants(
          selectedPassport,
          drafts.map((draft) => ({ name: draft.name, parameters: draft.parameters })),
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
  }, [drafts, selectedPassport]);

  const activeDraft = drafts.find((draft) => draft.id === activeId) ?? null;
  const dirty = activeDraft ? isDirty(activeDraft) : false;

  // Чувствительность посчитана для конкретного черновика, а не для вкладки
  // вообще: переключение (клик, дублирование, удаление активного) прячет
  // таблицу соседа вместо того, чтобы показывать её под чужим заголовком.
  useEffect(() => {
    if (activeId === sensitivityForId) return;
    setSensitivity([]);
    sensitivityRequestId.current += 1;
  }, [activeId, sensitivityForId]);

  // Совпадают состав и порядок id — тогда `results` точно про текущие
  // черновики, а не про то, что было до последнего добавления/удаления.
  const resultsMatchDrafts =
    resultsForIds.length === drafts.length && resultsForIds.every((id, index) => id === drafts[index]?.id);
  const activeResultIndex = resultsMatchDrafts ? resultsForIds.indexOf(activeId) : -1;
  const activeEconomics = activeResultIndex >= 0 ? results[activeResultIndex]?.economics ?? null : null;

  const volume = activeEconomics && activeEconomics.block_volume_m3 > 0 ? activeEconomics.block_volume_m3 : null;
  const groups = useMemo(() => (activeEconomics ? buildEstimate(activeEconomics) : []), [activeEconomics]);

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
  // Ревизия, на которой реально посчитан ТЕКУЩИЙ результат (`activeEconomics`),
  // а не ревизия паспорта на момент его создания — справочники могли
  // обновиться позже, и тогда `activeEconomics.reference_revision_id` новее.
  // Идёт в шапку сценариев (`EconomicsHeader`).
  const displayedRevisionId = activeEconomics?.reference_revision_id ?? passport?.reference_revision_id ?? "";
  const revisionLabel = useMemo(
    () => formatRevisionLabel(displayedRevisionId, revisions),
    [displayedRevisionId, revisions],
  );
  // Ревизия самого паспорта на момент его создания — идёт в `PassportStrip`
  // (поле подписано «Ревизия справочников паспорта»), а не ревизия текущего
  // расчёта: они расходятся, как только справочники публикуют новую ревизию
  // после создания паспорта.
  const passportRevisionLabel = useMemo(
    () => formatRevisionLabel(revisionId, revisions),
    [revisionId, revisions],
  );
  const passportContextLabel = passport ? `Паспорт вер. ${passport.version_no}` : "";

  const exportUrl = activeDraft?.sourceRunId ? api.blockEconomics.exportUrl(activeDraft.sourceRunId) : null;

  /**
   * Патчит параметры конкретного черновика по его id, а не «текущего
   * активного» (в отличие от прежней `patchActive`, которая читала
   * `current.activeId` внутри `setDraftsState` — в момент ПРИМЕНЕНИЯ патча,
   * а не в момент, когда асинхронная операция, вызвавшая этот патч, начала
   * выполняться). `renderEstimateGroup` передаёт сюда `activeDraft.id`,
   * захваченный в замыкании `onChange` заново при каждом рендере — обычные
   * синхронные правки (`NumericInput` и т.п.) бьют по актуальному черновику
   * в тот же тик, что и рендер, а асинхронные операции (`await fetch`),
   * начатые в старом инстансе раздела до его размонтирования по смене
   * `key={activeId}`, патчат именно тот черновик, с которого начинались, —
   * даже если сметчик успел переключиться на другой, пока запрос летел.
   */
  function patchDraft(draftId: string, patch: Partial<ModelParameters>) {
    setDraftsState((current) => ({
      ...current,
      drafts: current.drafts.map((draft) =>
        draft.id === draftId ? { ...draft, parameters: { ...draft.parameters, ...patch } } : draft,
      ),
    }));
  }

  function selectDraft(id: string) {
    setDraftsState((current) => ({ ...current, activeId: id }));
  }

  /**
   * Копия активного черновика становится активной: сравнивают её с исходным,
   * меняя одно поле. Список и активный id меняются одним `setState`, а не
   * двумя — иначе два быстрых клика подряд читают один и тот же список,
   * ещё не увидевший первое изменение, и одно из двух действий теряется.
   */
  function duplicateActive() {
    setDraftsState((current) => {
      const base = current.drafts.find((draft) => draft.id === current.activeId);
      if (!base || current.drafts.length >= MAX_VARIANTS) return current;
      const next = draftFromDefaults(`Вариант ${current.drafts.length + 1}`, { ...base.parameters });
      return { drafts: [...current.drafts, next], activeId: next.id };
    });
  }

  /**
   * Пересобрать активный черновик с параметров по умолчанию — выход из
   * состояния, когда его параметры страница отобразить не смогла (см.
   * `EconomicsErrorBoundary`). Сохранённые прогоны не трогаются: в «Истории»
   * они остаются как есть.
   */
  function resetActiveDraft() {
    if (!defaults) return;
    setDraftsState((current) => {
      const active = current.drafts.find((draft) => draft.id === current.activeId);
      const next = draftFromDefaults(active?.name ?? "Вариант 1", { ...defaults.parameters });
      const drafts = current.drafts.length
        ? current.drafts.map((draft) => (draft.id === current.activeId ? next : draft))
        : [next];
      return { drafts, activeId: next.id };
    });
  }

  function removeDraft(id: string) {
    setDraftsState((current) => {
      if (current.drafts.length <= 1) return current;
      const next = current.drafts.filter((draft) => draft.id !== id);
      return {
        drafts: next,
        activeId: id === current.activeId ? next[0]?.id ?? "" : current.activeId,
      };
    });
  }

  function renameDraft(id: string, name: string) {
    setDraftsState((current) => ({
      ...current,
      drafts: current.drafts.map((draft) => (draft.id === id ? { ...draft, name } : draft)),
    }));
  }

  /** Услуга уходит в правила затрат новой ревизией и исчезает из параметров активного черновика: иначе двойной счёт. */
  async function moveServiceToReference(index: number) {
    const service = activeDraft?.parameters.services[index];
    if (!service || !activeId) return;
    // Захватываем цель до `await`: пока публикация ревизии шла, сметчик мог
    // переключить вкладку/черновик — услуга должна уйти из того черновика,
    // с которого она реально ушла в справочник, а не из того, что стал
    // активным к моменту ответа.
    const draftId = activeId;
    setMovingService(service.name);
    setError("");
    try {
      const moved = await api.blockEconomics.serviceToReference(service);
      setDraftsState((current) => ({
        ...current,
        drafts: current.drafts.map((draft) =>
          draft.id === draftId
            ? {
                ...draft,
                parameters: {
                  ...draft.parameters,
                  services: draft.parameters.services.filter((item) => item !== service),
                },
              }
            : draft,
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

  async function saveActive(name: string) {
    if (!activeDraft || !selectedPassport) return;
    // Захватываем черновик и снимок параметров ДО await: пока сохранение
    // летит на сервер, поля сметы остаются редактируемыми, и `activeDraft`/
    // `current.activeId` на момент ответа могут указывать уже на другой
    // черновик или на другой снимок параметров того же черновика.
    const draftId = activeDraft.id;
    const submittedParameters = activeDraft.parameters;
    setBusy(true);
    setError("");
    try {
      const run = await api.blockEconomics.saveRun(selectedPassport, submittedParameters, name);
      setDraftsState((current) => ({
        ...current,
        drafts: current.drafts.map((draft) =>
          draft.id === draftId ? markSavedIfCurrent(draft, run.id, submittedParameters) : draft,
        ),
      }));
      setRuns(await api.blockEconomics.runs(selectedPassport));
      setStatus(`Сохранён как «${name}»`);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Не удалось сохранить сценарий.");
    } finally {
      setBusy(false);
    }
  }

  /**
   * Открыть сохранённый прогон черновиком: заменяет активную вкладку свежими
   * параметрами прогона, а не добавляет новую — иначе повторный выбор того
   * же прогона в шапке плодил бы вкладки без ограничения. Несохранённая
   * правка активной вкладки при этом теряется, поэтому если черновик
   * «грязный» (не совпадает с последним сохранённым снимком), сначала
   * спрашиваем подтверждение — иначе замена происходит сразу.
   */
  async function openRun(runId: string) {
    if (!selectedPassport) return;
    if (activeDraft && isDirty(activeDraft)) {
      const confirmed = window.confirm(
        `Черновик «${activeDraft.name}» не сохранён. Открыть другой сценарий и потерять несохранённые правки?`,
      );
      if (!confirmed) return;
    }
    // Паспорт мог смениться, пока прогон грузился (сметчик открыл прогон
    // паспорта A, затем переключился на паспорт B до ответа) — тогда ответ
    // устарел и не должен подменить черновик уже выбранного паспорта B.
    const passportAtStart = selectedPassport;
    setBusy(true);
    setError("");
    try {
      const run = await api.blockEconomics.run(runId);
      if (passportAtStart !== selectedPassportRef.current) return;

      // Недостающие поля старого прогона дополняются умолчаниями ЕГО пакета
      // работ, а не того, что открыт сейчас. Пакетов несколько (полный
      // комплекс БВР, контурные работы и другие), состав бригады и техника у
      // них разные: каталог активного пакета подставил бы в чужой сценарий
      // чужую бригаду, а перечитывание каталога следом уже собранные
      // параметры не исправляет. Каталог того же пакета заодно сохраняется в
      // состояние — тогда эффект ниже не пойдёт за ним второй раз.
      let fallback = defaultsRef.current;
      if (fallback?.parameters.package_code !== run.package_code) {
        try {
          const loaded = await api.blockEconomics.modelDefaults(passportAtStart, run.package_code);
          if (passportAtStart !== selectedPassportRef.current) return;
          fallback = loaded;
          setDefaults(loaded);
        } catch {
          // Каталог чужого пакета не подгрузился: заполнять недостающие поля
          // умолчаниями активного пакета нельзя — они относятся к другим
          // работам. Пустые значения видны в смете нулями, чужие числа — нет.
          fallback = null;
        }
      }

      const draft = draftFromRun(run, run.name, fallback?.parameters ?? null);
      setDraftsState((current) => {
        const index = current.drafts.findIndex((item) => item.id === current.activeId);
        const nextDrafts =
          index >= 0
            ? current.drafts.map((item, position) => (position === index ? draft : item))
            : [...current.drafts, draft];
        return { drafts: nextDrafts, activeId: draft.id };
      });
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Не удалось открыть сценарий.");
    } finally {
      setBusy(false);
    }
  }

  async function computeSensitivity() {
    if (!activeDraft || !selectedPassport) return;
    const id = ++sensitivityRequestId.current;
    // Пока считаем, сметчик мог переключить вкладку: ответ по старому
    // черновику не должен лечь в таблицу под новым активным заголовком.
    const forId = activeDraft.id;
    setSensitivityBusy(true);
    try {
      const response = await api.blockEconomics.sensitivity(selectedPassport, activeDraft.parameters);
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
