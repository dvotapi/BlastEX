import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api } from "../../api/endpoints";
import { buildEstimate } from "./estimateModel";
import { draftFromDefaults, draftFromRun, isDirty, markSavedIfCurrent, type Draft } from "./scenario";
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

/**
 * Состояние расчёта блока: паспорт, каталог умолчаний, черновики сценариев,
 * результаты модели, история прогонов. Вынесено из `BlockEconomicsPage`, чтобы
 * им пользовались и смета, и страница «Бурение» — один активный черновик на
 * обе страницы (см. `Docs/plans/2026-10-30-task-010-drilling-payroll-page.md`).
 */

const DEFAULT_PACKAGE = "DRILL_AND_BLAST";
const RECALC_DELAY_MS = 300;

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

/**
 * `requestKey` растёт при каждом новом запросе открыть тот же паспорт (кнопка
 * «в экономику» в листе «Расчёт»): сессия живёт между заходами, и без него
 * повторный запрос с тем же `passportId` не менял бы выбранный паспорт.
 */
export function useBlockEconomicsSession(passportId?: string | null, requestKey = 0) {
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
  // Растёт при `refresh`: заставляет пересчитать текущие черновики на свежих справочниках.
  const [refreshTick, setRefreshTick] = useState(0);
  const [busy, setBusy] = useState(false);
  const [sensitivityBusy, setSensitivityBusy] = useState(false);
  const [error, setError] = useState("");
  const [status, setStatus] = useState("");
  const [movingService, setMovingService] = useState("");
  // Подписи вместо кодов: имена объектов по ревизии паспорта и номера ревизий.
  const [siteNames, setSiteNames] = useState<Record<string, Record<string, string>>>({});
  const [revisions, setRevisions] = useState<ReferenceRevision[]>([]);
  const requestId = useRef(0);
  const defaultsRequestId = useRef(0);
  const sensitivityRequestId = useRef(0);
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
  }, [passportId, requestKey]);

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
   * Сессия живёт между заходами на страницы, а справочники за это время могли
   * получить новую ревизию: перечитываем каталог и список прогонов, черновики
   * не трогаем и пересчитываем на свежих данных. Пока первая загрузка не
   * закончилась, ничего не делает — она и так читает свежее.
   */
  const refresh = useCallback(() => {
    if (!defaultsRef.current || !selectedPassportRef.current) return;
    void reloadDefaults();
    const passportAtStart = selectedPassportRef.current;
    api.blockEconomics
      .runs(passportAtStart)
      .then((saved) => {
        if (passportAtStart === selectedPassportRef.current) setRuns(saved);
      })
      .catch(() => {
        // Прежний список прогонов остаётся.
      });
    setRefreshTick((tick) => tick + 1);
  }, [reloadDefaults]);

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
  }, [drafts, selectedPassport, refreshTick]);

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
  return {
    passports,
    selectedPassport,
    setSelectedPassport,
    defaults,
    drafts,
    activeId,
    activeDraft,
    dirty,
    results,
    runs,
    selectedRuns,
    setSelectedRuns,
    compare,
    sensitivity,
    busy,
    sensitivityBusy,
    error,
    status,
    movingService,
    resultsMatchDrafts,
    activeEconomics,
    volume,
    groups,
    passport,
    siteLabel,
    revisionLabel,
    passportRevisionLabel,
    passportContextLabel,
    exportUrl,
    reloadDefaults,
    refresh,
    patchDraft,
    selectDraft,
    duplicateActive,
    resetActiveDraft,
    removeDraft,
    renameDraft,
    moveServiceToReference,
    saveActive,
    openRun,
    computeSensitivity,
    compareRuns,
  };
}

export type BlockEconomicsSession = ReturnType<typeof useBlockEconomicsSession>;
