import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { api } from "../api/endpoints";
import { useWorkspace } from "../app/useWorkspace";
import { useTopbarSlot } from "../app/topbarSlot";
import { explosiveColor } from "../components/holeDrawing/palette";
import {
  applyCalcInputs,
  collectCalcInputs,
  defaultCalcSheet,
  defaultPanelInputs,
  isOptimizationResultStale,
  panelInputsEqual,
  DEFAULT_EXPLOSIVE_1,
  DEFAULT_EXPLOSIVE_2,
  DEFAULT_UNDERCHARGE_1_M,
  DEFAULT_UNDERCHARGE_2_M,
  type CalcInputsCatalogs,
  type PanelInputs,
  type SheetState,
} from "./calc/calcInputs";
import { CalcHelp } from "./calc/CalcHelp";
import { ChargeComparison } from "./calc/ChargeComparison";
import { CalcTopStrip, ReferenceWarnings } from "./calc/CalcTopStrip";
import { geometryPayload, type VariantContext } from "./calc/holeGeometryPayload";
import { MetricChips } from "./calc/MetricChips";
import { knownUnitCode, unitForLoadedSheet } from "./calc/unitSelection";
import { PassportBar } from "./calc/PassportBar";
import { ResultsChart } from "./calc/ResultsChart";
import { useHoleGeometry } from "./calc/useHoleGeometry";
import { useCalcInputsAutosave } from "./calc/useCalcInputsAutosave";
import { KuzRamDialog, type KuzRamSource } from "./calc/kuzram/KuzRamDialog";
import { ThresholdFlag } from "./calc/kuzram/ThresholdFlag";
import { formatOversize, formatQ } from "./calc/kuzram/kuzramFormat";
import {
  defaultKuzramBlock,
  kuzramSettingsOf,
  KUZRAM_RECALC_DELAY_MS,
  optimizeErrorText,
  outdatedHint,
  settingsCaption,
  type KuzRamBlock,
  type KuzRamFact,
  type OptimizeError,
} from "./calc/kuzram/kuzramSettings";
import type { BlastVariant, Explosive, KuzRamFactInput, KuzRamSettings, ProductionUnit, Rock } from "../types";

/** Сколько раз повторить пересчёт по правке настроек, если лист правят, пока
 * летит запрос: каждый повтор требует новой правки, предел — страховка от
 * бесконечного цикла при будущей правке условий. */
const KUZRAM_RECALC_ATTEMPTS = 3;

function FullBvrCalc({
  onSendToDesign,
  onOpenEconomics,
}: {
  onSendToDesign?: (variant: BlastVariant) => void;
  onOpenEconomics?: (passportId: string) => void;
}) {
  const [rocks, setRocks] = useState<Rock[]>([]);
  const [explosives, setExplosives] = useState<Explosive[]>([]);
  const [rockName, setRockNameRaw] = useState("");
  const [explosiveKey, setExplosiveKeyRaw] = useState("");
  const [lumpSize, setLumpSizeRaw] = useState(400);
  const [benchHeight, setBenchHeightRaw] = useState(10);
  const [overdrill, setOverdrillRaw] = useState(1);
  const [oversizeCoeff, setOversizeCoeffRaw] = useState(1.05);
  const [spacing, setSpacingRaw] = useState(1.25);
  const [threshold, setThresholdRaw] = useState(5);
  const [allCrowns, setAllCrowns] = useState<number[]>([]);
  const [selectedCrowns, setSelectedCrownsRaw] = useState<number[]>([]);
  // Растёт при каждой правке поля, влияющего на `api.optimize` (порода, ВВ,
  // кондиционный кусок, высота уступа, перебур, коэффициенты, порог
  // негабарита, выбранные коронки, настройки модели Kuz-Ram) — включая
  // применение загруженного листа. Ответ расчёта, запущенного на одном
  // значении счётчика, отбрасывается, если к моменту ответа счётчик уже
  // другой: лист успели поправить, пока ответ летел, и метрики в ответе —
  // уже про прежние значения полей.
  const optimizeGenerationRef = useRef(0);
  const bumpOptimizeGeneration = useCallback(() => {
    optimizeGenerationRef.current += 1;
  }, []);
  // Номер последнего запущенного подбора: флаг «идёт расчёт» снимает только
  // он — иначе ранний ответ погасил бы «Пересчёт…», пока летит новый запрос.
  const optimizeRunRef = useRef(0);
  // Номер загрузки объекта (растёт в начале каждой): отложенный пересчёт по
  // правке настроек сверяет его, а не только имя — после А → Б → А лист ещё
  // может быть от Б, пока идёт повторная загрузка А.
  const objectLoadRef = useRef(0);
  const setRockName = useCallback(
    (value: string) => { setRockNameRaw(value); bumpOptimizeGeneration(); },
    [bumpOptimizeGeneration],
  );
  const setExplosiveKey = useCallback(
    (value: string) => { setExplosiveKeyRaw(value); bumpOptimizeGeneration(); },
    [bumpOptimizeGeneration],
  );
  const setLumpSize = useCallback(
    (value: number) => { setLumpSizeRaw(value); bumpOptimizeGeneration(); },
    [bumpOptimizeGeneration],
  );
  const setBenchHeight = useCallback(
    (value: number) => { setBenchHeightRaw(value); bumpOptimizeGeneration(); },
    [bumpOptimizeGeneration],
  );
  const setOverdrill = useCallback(
    (value: number) => { setOverdrillRaw(value); bumpOptimizeGeneration(); },
    [bumpOptimizeGeneration],
  );
  const setOversizeCoeff = useCallback(
    (value: number) => { setOversizeCoeffRaw(value); bumpOptimizeGeneration(); },
    [bumpOptimizeGeneration],
  );
  const setSpacing = useCallback(
    (value: number) => { setSpacingRaw(value); bumpOptimizeGeneration(); },
    [bumpOptimizeGeneration],
  );
  const setThreshold = useCallback(
    (value: number) => { setThresholdRaw(value); bumpOptimizeGeneration(); },
    [bumpOptimizeGeneration],
  );
  const setSelectedCrowns = useCallback(
    (value: number[] | ((prev: number[]) => number[])) => {
      setSelectedCrownsRaw(value);
      bumpOptimizeGeneration();
    },
    [bumpOptimizeGeneration],
  );
  // Блок модели Kuz-Ram объекта: настройки подбора q и фактические взрывы.
  const [kuzram, setKuzram] = useState<KuzRamBlock>(defaultKuzramBlock);
  // Растёт при каждой правке настроек модели в окне — эффект ниже
  // перезапускает подбор. Загрузка листа её не трогает: там подбор идёт сам.
  const [kuzramRevision, setKuzramRevision] = useState(0);
  // Для отложенного пересчёта: новая правка настроек отменяет попытки прежней.
  const kuzramRevisionRef = useRef(kuzramRevision);
  kuzramRevisionRef.current = kuzramRevision;
  // До какой ревизии настроек варианты досчитаны: растёт только от применённого
  // ответа подбора, начатого на этой ревизии, — в том числе ручного «Рассчитать
  // варианты». Ошибка подбора её не двигает: варианты остались прежними. Пока
  // отстаёт, варианты — по прежним настройкам.
  const [calculatedKuzramRevision, setCalculatedKuzramRevision] = useState(0);
  // Идёт пауза перед пересчётом по правке настроек или его попытки.
  const [kuzramPending, setKuzramPending] = useState(false);
  const [kuzramOpen, setKuzramOpen] = useState(false);
  const setKuzramSettings = useCallback(
    (next: KuzRamSettings) => {
      setKuzram((current) => ({ ...kuzramSettingsOf(next), facts: current.facts }));
      bumpOptimizeGeneration();
      setKuzramRevision((value) => value + 1);
      // Вместе с ревизией, а не в эффекте: запись C(A) из ответа сервера идёт
      // не из события ввода, и эффект сработал бы уже после отрисовки кадра
      // «варианты по прежним настройкам» без «Пересчёт…».
      setKuzramPending(true);
    },
    [bumpOptimizeGeneration],
  );
  const setKuzramFacts = useCallback((facts: KuzRamFact[]) => {
    // Факты подбор не трогают: ни счётчик поколений, ни ревизия настроек не растут.
    setKuzram((current) => ({ ...current, facts }));
  }, []);
  const [nsiLengthOptions, setNsiLengthOptions] = useState<number[]>([12]);
  const [detonatorDelayOptions, setDetonatorDelayOptions] = useState<number[]>([500]);
  const [variants, setVariants] = useState<BlastVariant[]>([]);
  // Порог, с которым посчитаны варианты: «> порога» сравнивается с ним, а не
  // с ползунком, который могли сдвинуть без пересчёта.
  const [variantsThresholdPct, setVariantsThresholdPct] = useState<number | null>(null);
  const [selectedIndex, setSelectedIndex] = useState(0);
  const [blockVolumeM3, setBlockVolumeM3] = useState(30_000);
  const [additionalHolesPct, setAdditionalHolesPct] = useState(3.0);
  // Юнит в шапке — фильтр списка объектов (см. `unitSelection.ts`). Хранится
  // за объектом вместе с остальными настройками листа.
  const [productionUnitCode, setProductionUnitCode] = useState("");
  const [units, setUnits] = useState<ProductionUnit[]>([]);
  // Фильтр, действовавший в момент выбора объекта в шапке: у объекта без
  // юнита лист после загрузки не должен сбрасывать фильтр на сохранённый.
  const carriedUnitRef = useRef<string | null>(null);
  // Юнит, который надо поставить загруженному листу вместо сохранённого (юнит
  // объекта или перенесённый фильтр). Ставится после отсечки автосохранения —
  // как обычная правка, иначе он не записался бы и пропал после перезагрузки.
  const pendingUnitRef = useRef<string | null>(null);
  // Справочники не пришли: держится до перезагрузки страницы — без них объект
  // не грузится, а повторного запроса нет.
  const [referencesError, setReferencesError] = useState("");
  // Настройки листа активного объекта не прочитались; загрузка следующего сбрасывает.
  const [sheetLoadError, setSheetLoadError] = useState("");
  // Ошибка подбора — с ревизией настроек модели, на которой он запущен: по
  // ней видно, ошибка это текущих настроек или прошлого расчёта
  // (`optimizeErrorText`). Загрузка объекта сбрасывает: ошибка — про его лист.
  const [optimizeError, setOptimizeError] = useState<OptimizeError | null>(null);
  const [busy, setBusy] = useState(false);
  // Поля вариантов заряда: карточки ведут их у себя, а сюда сообщают об
  // изменениях — из них собираются настройки листа и запросы схем заряда.
  const [panelInputs, setPanelInputs] = useState<{ left: PanelInputs; right: PanelInputs }>(() => ({
    left: defaultPanelInputs(DEFAULT_EXPLOSIVE_1, DEFAULT_UNDERCHARGE_1_M),
    right: defaultPanelInputs(DEFAULT_EXPLOSIVE_2, DEFAULT_UNDERCHARGE_2_M),
  }));
  // Объект, настройки которого уже загружены. Пока он не совпал с активным,
  // лист «не готов»: автосохранение молчит, иначе умолчания затрут сохранённое.
  const [loadedObjectName, setLoadedObjectName] = useState<string | null>(null);
  // Диаметр из загруженных настроек: пока вариантов нет (расчёт не запускался
  // или автозапуск упал), сохраняем его, а не `null` — иначе выбор диаметра
  // потерялся бы при первой же записи автосохранения.
  const [loadedCrownMm, setLoadedCrownMm] = useState<number | null>(null);

  const {
    state,
    setActiveWorkObjectName,
    error: workspaceError,
    loading: workspaceLoading,
  } = useWorkspace();
  const objectName = state?.settings.active_work_object_name ?? "";
  const objects = state?.references.work_object_records ?? [];
  // Для загрузки листа в эффекте, который не перезапускается от смены списка.
  const objectsRef = useRef(objects);
  objectsRef.current = objects;
  const unitCode = knownUnitCode(units, productionUnitCode);
  const ready = loadedObjectName !== null && loadedObjectName === objectName;
  // Актуальное имя объекта для проверок «не устарел ли расчёт» в замыканиях,
  // которые не перевызываются при каждом рендере (например, `calculate()`,
  // запущенный до смены объекта).
  const objectNameRef = useRef(objectName);
  objectNameRef.current = objectName;
  // Узел в шапке приложения: если он есть, полоса переезжает туда через
  // createPortal (см. topbarSlot.tsx); иначе рисуется на своём обычном
  // месте на странице (например, вне AppShell).
  const topbarSlot = useTopbarSlot();

  // Умолчания справочников: нужны листу без сохранённых настроек.
  const [referenceDefaults, setReferenceDefaults] = useState<{ rockName: string; explosiveKey: string } | null>(null);

  useEffect(() => {
    Promise.all([api.rocks(), api.explosives(), api.blastOptions()]).then(([rockData, explosiveData, opts]) => {
      setRocks(rockData.items);
      setExplosives(explosiveData.items);
      setRockName(rockData.default_name);
      setExplosiveKey(explosiveData.default_key);
      setReferenceDefaults({ rockName: rockData.default_name, explosiveKey: explosiveData.default_key });
      setAllCrowns(opts.crown_diameters_mm);
      setSelectedCrowns(opts.crown_diameters_mm);
      setNsiLengthOptions(opts.nsi_length_options_m);
      setDetonatorDelayOptions(opts.detonator_delay_ms_options);
    }).catch((reason) => setReferencesError(reason instanceof Error ? reason.message : "Не удалось загрузить справочники."));
    // Отдельно от справочников расчёта: без юнитов лист работает, поле просто
    // не показывается.
    api.productionUnits().then((data) => setUnits(data.items)).catch(() => setUnits([]));
  }, []);

  const rock = useMemo(() => rocks.find((r) => r.name === rockName), [rocks, rockName]);
  const explosive = useMemo(() => explosives.find((e) => e.key === explosiveKey), [explosives, explosiveKey]);
  const selected = variants[selectedIndex];
  // Актуальная выбранная коронка для `preferredCrownMm` подбора по правке
  // настроек модели: клик по другой строке, случившийся в паузе перед
  // запросом или пока он летит, не должен откатиться к коронке, выбранной на
  // момент планирования таймера (см. `runOptimize` и эффект ниже).
  const selectedCrownRef = useRef<number | null>(null);
  selectedCrownRef.current = selected?.crown_mm ?? loadedCrownMm;

  /** Чем проверяются сохранённые настройки: пока справочники не пришли — нечем. */
  const catalogs: CalcInputsCatalogs | null = useMemo(
    () =>
      rocks.length && explosives.length && allCrowns.length
        ? {
            rocks: rocks.map((r) => r.name),
            explosiveKeys: explosives.map((e) => e.key),
            crowns: allCrowns,
            nsiLengthOptions,
            detonatorDelayOptions,
          }
        : null,
    [rocks, explosives, allCrowns, nsiLengthOptions, detonatorDelayOptions]
  );

  const sheet: SheetState = useMemo(
    () => ({
      rockName,
      explosiveKey,
      lumpSizeMm: lumpSize,
      benchHeightM: benchHeight,
      overdrillM: overdrill,
      oversizeCoeff,
      spacingCoeff: spacing,
      oversizeThresholdPct: threshold,
      selectedCrownsMm: selectedCrowns,
      selectedCrownMm: selected?.crown_mm ?? loadedCrownMm,
      blockVolumeM3,
      additionalHolesPct,
      productionUnitCode,
      kuzram,
      panels: panelInputs,
    }),
    [rockName, explosiveKey, lumpSize, benchHeight, overdrill, oversizeCoeff, spacing, threshold,
      selectedCrowns, selected, loadedCrownMm, blockVolumeM3, additionalHolesPct, productionUnitCode, panelInputs, kuzram]
  );
  const sheetInputs = useMemo(() => collectCalcInputs(sheet), [sheet]);
  // Актуальный лист для отложенного пересчёта по правке настроек модели.
  const sheetRef = useRef(sheet);
  sheetRef.current = sheet;

  // Статус автосохранения показывает верхняя полоса листа (задача 5).
  const { status: autosaveStatus, flush } = useCalcInputsAutosave({ objectName, inputs: sheetInputs, ready });

  // После автосохранения: его эффект отсечки в том же коммите уже запомнил
  // загруженный лист, и смена юнита здесь уйдёт в запись.
  useEffect(() => {
    if (!ready || pendingUnitRef.current === null) return;
    setProductionUnitCode(pendingUnitRef.current);
    pendingUnitRef.current = null;
  }, [ready]);

  const applySheet = useCallback((next: SheetState) => {
    setRockName(next.rockName);
    setExplosiveKey(next.explosiveKey);
    setLumpSize(next.lumpSizeMm);
    setBenchHeight(next.benchHeightM);
    setOverdrill(next.overdrillM);
    setOversizeCoeff(next.oversizeCoeff);
    setSpacing(next.spacingCoeff);
    setThreshold(next.oversizeThresholdPct);
    setSelectedCrowns(next.selectedCrownsMm);
    setLoadedCrownMm(next.selectedCrownMm);
    setBlockVolumeM3(next.blockVolumeM3);
    setAdditionalHolesPct(next.additionalHolesPct);
    setProductionUnitCode(next.productionUnitCode);
    setPanelInputs(next.panels);
    setKuzram(next.kuzram);
  }, []);

  const variantContext: VariantContext | null = useMemo(
    () =>
      selected && rock
        ? {
            gridAM: selected.grid_a_m,
            gridBM: selected.grid_b_m,
            depthM: benchHeight + overdrill,
            overdrillM: overdrill,
            crownMm: selected.crown_mm,
            holeOversizeCoeff: oversizeCoeff,
            blockVolumeM3,
            additionalHolesPct: additionalHolesPct / 100,
          }
        : null,
    [selected, rock, benchHeight, overdrill, oversizeCoeff, blockVolumeM3, additionalHolesPct],
  );
  // Схемы заряда обоих вариантов считаются здесь, из полей карточек, поднятых
  // в `panelInputs`: одна правда и для таблиц сравнения, и для паспорта.
  const leftGeometry = useHoleGeometry(variantContext ? geometryPayload(panelInputs.left, variantContext) : null);
  const rightGeometry = useHoleGeometry(variantContext ? geometryPayload(panelInputs.right, variantContext) : null);
  /** Цвет ВВ варианта: есть и до ответа схемы — по записи справочника. */
  const variantColor = (inputs: PanelInputs) => {
    const record = explosives.find((item) => item.key === inputs.explosive_key);
    return explosiveColor(inputs.explosive_key, record?.name, record?.chart_label);
  };

  const handleLeftInputs = useCallback((next: PanelInputs) => {
    setPanelInputs((current) => (panelInputsEqual(current.left, next) ? current : { ...current, left: next }));
  }, []);
  const handleRightInputs = useCallback((next: PanelInputs) => {
    setPanelInputs((current) => (panelInputsEqual(current.right, next) ? current : { ...current, right: next }));
  }, []);

  function toggleCrown(value: number) {
    setSelectedCrowns((prev) => (prev.includes(value) ? prev.filter((c) => c !== value) : [...prev, value].sort((a, b) => a - b)));
  }

  /** Расчёт вариантов по переданному листу: он же считает при автозапуске,
   * когда состояние формы ещё не успело обновиться после загрузки настроек.
   * `preferredCrownMm` — сохранённый диаметр, если такой вариант найдётся;
   * геттер, а не значение, чтобы читать его в момент ответа, а не в момент
   * планирования запроса — иначе клик по другой строке в паузе перед
   * запросом или пока он летит откатился бы к прежней коронке.
   * `isStale` — автозапуск для объекта, который успели сменить: его результат
   * выбрасываем, иначе он затрёт варианты нового объекта.
   * Возвращает `false`, только если ответ выброшен как устаревший (или запуск
   * устарел ещё до запроса); ответ, ошибка или «считать нечего» — `true`.
   * Считать нечего (нет породы, ВВ или коронок) бывает только у пересчёта по
   * правке настроек модели: ручной запуск без них недоступен, а загруженный
   * лист их всегда подставляет. Ошибку прошлого расчёта это не трогает —
   * она помечена своей ревизией настроек. */
  async function runOptimize(
    source: SheetState,
    preferredCrownMm: () => number | null,
    isStale: () => boolean = () => false,
  ): Promise<boolean> {
    const sheetRock = rocks.find((r) => r.name === source.rockName);
    const sheetExplosive = explosives.find((e) => e.key === source.explosiveKey);
    // Лист и ревизия настроек меняются вместе, поэтому ответ по этому листу —
    // варианты по настройкам ревизии на момент запроса.
    const revisionAtStart = kuzramRevisionRef.current;
    const markCalculated = () => setCalculatedKuzramRevision((done) => Math.max(done, revisionAtStart));
    // Считать нечего — варианты на экране остались прежними, ревизию не двигаем.
    if (!sheetRock || !sheetExplosive || !source.selectedCrownsMm.length) return true;
    // Страховка (из #96): устаревший запуск не отправляем — иначе он стал бы
    // «последним» подбором, держал бы флаг расчёта и стёр бы ошибку уже нового
    // листа. Сейчас не срабатывает: все вызовы берут счётчик поколения прямо
    // перед вызовом. Нужна тому, кто возьмёт его раньше (например, в момент
    // постановки таймера, как было до пересчёта по свежему листу).
    if (isStale()) return false;
    const run = ++optimizeRunRef.current;
    setBusy(true);
    setOptimizeError(null);
    try {
      const result = await api.optimize({
        rock: sheetRock,
        explosive: sheetExplosive,
        lumpSize: source.lumpSizeMm,
        benchHeight: source.benchHeightM,
        overdrill: source.overdrillM,
        oversizeCoeff: source.oversizeCoeff,
        spacing: source.spacingCoeff,
        threshold: source.oversizeThresholdPct,
        crownDiametersMm: source.selectedCrownsMm,
        kuzram: kuzramSettingsOf(source.kuzram),
      });
      if (isStale()) return false;
      setVariants(result.variants);
      setVariantsThresholdPct(result.max_oversize_threshold_pct);
      const preferredValue = preferredCrownMm();
      const restored = preferredValue === null ? -1 : result.variants.findIndex((v) => v.crown_mm === preferredValue);
      const preferred = result.variants.findIndex((v) => v.crown_mm === 152);
      setSelectedIndex(restored >= 0 ? restored : preferred >= 0 ? preferred : 0);
      markCalculated();
      return true;
    } catch (reason) {
      if (isStale()) return false;
      setOptimizeError({ message: reason instanceof Error ? reason.message : "Ошибка расчёта.", revision: revisionAtStart });
      return true;
    } finally {
      // Параллельный подбор (правка настроек модели, пока летел прошлый) сам
      // снимет флаг — ранний ответ не должен гасить «идёт расчёт».
      if (run === optimizeRunRef.current) setBusy(false);
    }
  }

  /** Ручной запуск расчёта: если пользователь успел сменить объект или
   * поправить влияющее на расчёт поле, пока ответ ещё летел, результат —
   * уже не про текущий лист, и его нужно отбросить (как и автозапуск после
   * загрузки настроек — `isStale` в `runOptimize`). */
  async function calculate() {
    const requestedObjectName = objectName;
    const startedGeneration = optimizeGenerationRef.current;
    await runOptimize(sheet, () => null, () =>
      isOptimizationResultStale(
        startedGeneration,
        optimizeGenerationRef.current,
        requestedObjectName,
        objectNameRef.current,
      ),
    );
  }

  // Правка настроек модели в окне пересчитывает варианты сама — с паузой,
  // чтобы набор числа по цифрам не слал запрос на каждую. В отличие от
  // ручного `calculate()`, выбранную коронку не сбрасываем — считаем с той
  // же `preferredCrownMm`, что и сейчас на листе, иначе выбор прыгал бы на
  // Ø152 при каждой правке.
  //
  // Пересчёт по правке настроек обещан, поэтому лист берём в момент запроса
  // (`sheetRef`), а не планирования таймера, и повторяем запрос, если лист
  // поправили, пока он летел: иначе ответ отбросится как устаревший, а
  // варианты останутся посчитанными по прежним настройкам при погасшем
  // «Пересчёт…». Смена объекта или новая правка настроек (у неё свой таймер)
  // останавливают попытки ещё до запроса: запрос по листу прежнего объекта
  // стал бы последним и не дал бы ответу нового снять «идёт расчёт».
  // Попытки кончились, а ответ так и не применён — ревизия остаётся
  // непосчитанной, и окно говорит, что варианты по прежним настройкам, пока
  // их не пересчитают вручную.
  useEffect(() => {
    if (kuzramRevision === 0) return;
    const revision = kuzramRevision;
    const requestedObjectName = objectName;
    const load = objectLoadRef.current;
    const current = () =>
      objectLoadRef.current === load &&
      objectNameRef.current === requestedObjectName &&
      kuzramRevisionRef.current === revision;
    const timer = window.setTimeout(() => {
      void (async () => {
        try {
          for (let attempt = 0; attempt < KUZRAM_RECALC_ATTEMPTS && current(); attempt += 1) {
            const startedGeneration = optimizeGenerationRef.current;
            const applied = await runOptimize(sheetRef.current, () => selectedCrownRef.current, () =>
              isOptimizationResultStale(
                startedGeneration,
                optimizeGenerationRef.current,
                requestedObjectName,
                objectNameRef.current,
              ),
            );
            if (applied) break;
          }
        } finally {
          // Новая правка настроек сама ведёт свою паузу и попытки.
          if (kuzramRevisionRef.current === revision) setKuzramPending(false);
        }
      })();
    }, KUZRAM_RECALC_DELAY_MS);
    return () => window.clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [kuzramRevision]);

  /**
   * Настройки активного объекта: при появлении справочников и при каждой смене
   * объекта. Сначала дописываем отложенные изменения прошлого объекта, потом
   * читаем настройки нового. Есть сохранённые — применяем их и сразу считаем
   * варианты; нет — умолчания и без автозапуска. Лист считается готовым сразу
   * после применения загруженных (или умолчальных) значений — не дожидаясь
   * автозапуска варианта, который может идти долго; правка, сделанная за это
   * время, не потеряется, а результат автозапуска ляжет поверх неё как
   * обычная последующая правка. Запрос упал — показываем ошибку и умолчания,
   * но лист остаётся «не готовым»: писать поверх непрочитанного нельзя.
   */
  useEffect(() => {
    if (!catalogs || !referenceDefaults || !objectName) return;
    let cancelled = false;
    objectLoadRef.current += 1;
    setLoadedObjectName(null);
    setLoadedCrownMm(null);
    setVariants([]);
    setOptimizeError(null);
    setSheetLoadError("");
    // Подбор прежнего объекта отбросится как устаревший, но флаги сняли бы
    // только его ответ и конец его попыток — а у запросов нет таймаута, и новый
    // объект мог бы навсегда остаться с «Выполняется расчёт…» и «Пересчёт…»
    // (у объекта без сохранённого листа своего подбора, снявшего бы их, нет).
    // Подбор нового объекта или новая правка настроек поставят флаги заново,
    // и ответ прежнего их не погасит: «идёт расчёт» снимает только последний
    // запуск, а «Пересчёт…» — попытки своей ревизии.
    setBusy(false);
    setKuzramPending(false);
    // Перенесённый фильтр читается здесь, а очищается только после применения
    // листа: если смена объекта откатится, эффект запустится ещё раз (для
    // прежнего объекта), и фильтр должен дожить до этого запуска.
    const carriedUnit = carriedUnitRef.current;
    pendingUnitRef.current = null;
    /** Лист с юнитом загрузки; юнит, который надо записать, ждёт отсечки автосохранения. */
    const withUnit = (next: SheetState, saved: boolean): SheetState => {
      carriedUnitRef.current = null;
      const { unit, persist } = unitForLoadedSheet(objectsRef.current, objectName, carriedUnit, next.productionUnitCode, saved);
      if (persist) {
        pendingUnitRef.current = unit;
        return next;
      }
      return { ...next, productionUnitCode: unit };
    };
    void (async () => {
      await flush();
      try {
        const saved = await api.calcInputs(objectName);
        if (cancelled) return;
        const loaded = applyCalcInputs(saved.inputs, catalogs);
        const applied = loaded && withUnit(loaded, true);
        if (applied) {
          applySheet(applied);
          if (cancelled) return;
          // Отсечка «уже сохранено» — сразу после применения загруженного
          // листа, а не после (возможно долгого) автозапуска ниже: иначе
          // лист был бы редактируемым, но `ready` ещё false, и правка,
          // сделанная за это время, не попала бы в автосохранение — а когда
          // `ready` наконец станет true, эта правка уже стала бы «текущим
          // значением», неотличимым от только что загруженного, и потерялась
          // бы. Результат автозапуска — обычная последующая правка поверх
          // этой отсечки, автосохранение её подхватит само.
          setLoadedObjectName(objectName);
          const startedGeneration = optimizeGenerationRef.current;
          await runOptimize(applied, () => applied.selectedCrownMm, () =>
            cancelled ||
            isOptimizationResultStale(startedGeneration, optimizeGenerationRef.current, objectName, objectNameRef.current),
          );
        } else {
          applySheet(withUnit(defaultCalcSheet(catalogs, referenceDefaults), false));
          if (cancelled) return;
          setLoadedObjectName(objectName);
        }
      } catch {
        if (cancelled) return;
        // Настройки не прочитались: значения прошлого объекта на листе были бы
        // чужими, поэтому открываем умолчания. `loadedObjectName` не ставим —
        // лист остаётся «не готовым», и автосохранение не затрёт умолчаниями
        // то, что мы не смогли прочитать.
        // Лист «не готов», автосохранения не будет — юнит только на экран.
        applySheet(withUnit(defaultCalcSheet(catalogs, referenceDefaults), false));
        setSheetLoadError(
          "Не удалось загрузить настройки листа — открыты значения по умолчанию, " +
            "автосохранение выключено до перезагрузки страницы.",
        );
      }
    })();
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [catalogs, referenceDefaults, objectName]);

  const topStrip = (
    <CalcTopStrip
      variant={topbarSlot ? "topbar" : "page"}
      objectName={objectName}
      objects={objects}
      units={units}
      unitCode={unitCode}
      onUnitChange={setProductionUnitCode}
      onObjectChange={(name) => {
        // Переносим только видимый фильтр: пока юниты не загружены (или не
        // загрузились), поля «Юнит» нет, и пустой фильтр затёр бы сохранённый.
        carriedUnitRef.current = units.length ? unitCode : null;
        void setActiveWorkObjectName(name);
      }}
      autosaveStatus={autosaveStatus}
      workspaceLoading={workspaceLoading}
      sheetReady={ready}
    />
  );

  const metrics = {
    q: selected ? selected.specific_q_kg_m3 : null,
    w: selected ? selected.line_of_least_resistance_m : null,
    x50: selected ? selected.x50_mm : null,
    oversize: selected ? selected.oversize_pct : null,
  };
  const kuzramCaption = settingsCaption(kuzram);
  const kuzramBusy = busy || kuzramPending;
  // Варианты не по текущим настройкам модели, и пересчёт не идёт. Пока лист
  // не готов (грузятся настройки другого объекта) или вариантов нет,
  // помечать нечего. Счётчики ревизий общие для всех объектов, но при смене
  // объекта варианты сбрасываются — пометка к ним не переходит.
  const kuzramOutdated = ready && variants.length > 0 && calculatedKuzramRevision < kuzramRevision && !kuzramBusy;
  // Совет к пометке — одинаковый на листе и в окне. К сообщению об ошибке он
  // ведёт, только если это ошибка текущих настроек модели.
  const kuzramOutdatedHint = kuzramOutdated
    ? outdatedHint(optimizeError?.revision === kuzramRevision, {
        crowns: !selectedCrowns.length,
        rock: !rock,
        explosive: !explosive,
      })
    : null;
  // Пока идёт пауза перед пересчётом по правке настроек (или его попытки),
  // ошибку сотрёт сам запрос: приставка «прошлый расчёт» только мелькнула бы,
  // а alert зачитался бы заново посреди ввода.
  const optimizeErrorMessage = kuzramPending
    ? (optimizeError?.message ?? "")
    : optimizeErrorText(optimizeError, kuzramRevision);
  const sheetErrors = [referencesError, sheetLoadError, optimizeErrorMessage, workspaceError].filter(Boolean);
  const kuzramSource: KuzRamSource = {
    rockName,
    explosiveName: explosive?.name ?? explosiveKey,
    benchHeightM: benchHeight,
    overdrillM: overdrill,
    lumpSizeMm: lumpSize,
    thresholdPct: threshold,
    crownsMm: selectedCrowns,
  };
  // Пока запрос летит, пользователь мог поправить настройки модели в окне
  // (сам подбор их не трогает), поправить лист (даже закрыв окно) или сменить
  // объект — тогда ответ, пусть и успешный, уже не про текущие настройки и не
  // про этот объект: записывать его C(A) поверх свежих значений нельзя
  // (`KuzRamFacts` покажет причину как обычную ошибку подбора). Счётчик
  // поколений растёт от правки любого поля, влияющего на расчёт (не только
  // настроек модели), поэтому ловит и правку листа после закрытия окна.
  const calibrateKuzram = async (facts: KuzRamFactInput[]) => {
    if (!rock || !explosive) throw new Error("Выберите породу и ВВ на листе.");
    const requestedObjectName = objectName;
    const startedGeneration = optimizeGenerationRef.current;
    const response = await api.calibrateKuzram({
      rock,
      explosive,
      lumpSize,
      benchHeight,
      overdrill,
      oversizeCoeff,
      spacing,
      kuzram: kuzramSettingsOf(kuzram),
      facts,
    });
    if (objectNameRef.current !== requestedObjectName || optimizeGenerationRef.current !== startedGeneration) {
      throw new Error("Настройки модели или объект изменились, пока шёл подбор, — C(A) не записана. Запустите подбор ещё раз.");
    }
    return response;
  };

  return (
    <div className="calc-sheet">
      {topbarSlot ? createPortal(topStrip, topbarSlot) : topStrip}
      <CalcHelp />
      {sheetErrors.length > 0 && (
        <div className="calc-errors">
          {/* Тексты разных ошибок могут совпасть (сообщение сети) — ключ по месту. */}
          {sheetErrors.map((message, index) => <div key={index} className="page-error" role="alert">{message}</div>)}
        </div>
      )}
      <div className="calc-top-row">
        <section className="panel input-panel">
          <header>
            <b>Исходные данные</b>
            <ReferenceWarnings warnings={state?.warnings ?? []} />
          </header>
          <div className="panel-body input-panel-body">
            {/* Пока настройки объекта не загружены (`!ready`), правка любого
                поля пропала бы: `applySheet` при ответе перезапишет её своими
                значениями. Отключаем весь ввод на этот момент — `fieldset`
                выключает вложенные поля браузерными средствами, а `display:
                contents` оставляет его колонки прямыми детьми сетки панели. */}
            <fieldset className="input-panel-fieldset" disabled={!ready}>
              <div className="input-column">
                <label>Порода<select value={rockName} onChange={(e) => setRockName(e.target.value)}>{rocks.map((r) => <option key={r.id || r.name}>{r.name}</option>)}</select></label>
                <label>Взрывчатое вещество<select value={explosiveKey} onChange={(e) => setExplosiveKey(e.target.value)}>{explosives.map((ex) => <option key={ex.id || ex.key} value={ex.key}>{ex.name}</option>)}</select></label>
                <div className="field-triple">
                  <label title="Высота уступа, м">Уступ, м<input type="number" min={5} max={25} step={0.5} value={benchHeight} onChange={(e) => setBenchHeight(Number(e.target.value))} /></label>
                  <label title="Перебур, м">Перебур, м<input type="number" min={0} max={3} step={0.1} value={overdrill} onChange={(e) => setOverdrill(Number(e.target.value))} /></label>
                  <label title="Кондиционный кусок, мм">Кусок, мм<input type="number" min={100} max={1200} step={50} value={lumpSize} onChange={(e) => setLumpSize(Number(e.target.value))} /></label>
                </div>
              </div>
              <div className="input-column">
                <fieldset className="crown-select">
                  <legend>Диаметры коронок, мм</legend>
                  {allCrowns.map((c) => (
                    <label key={c} className="crown-checkbox">
                      <input type="checkbox" checked={selectedCrowns.includes(c)} onChange={() => toggleCrown(c)} /> {c}
                    </label>
                  ))}
                </fieldset>
                <button className="calculate-button" onClick={calculate} disabled={busy || !ready || !rock || !explosive || !selectedCrowns.length}>
                  {!ready ? "Загрузка настроек объекта…" : busy ? "Выполняется расчёт…" : "Рассчитать варианты"}
                </button>
              </div>
              <div className="slider-rows">
                <label className="slider-row"><span>Допустимый негабарит</span><input type="range" min={1} max={15} step={0.5} value={threshold} onChange={(e) => setThreshold(Number(e.target.value))} /><b>{threshold}%</b></label>
                <label className="slider-row"><span title="Коэффициент сетки a/W">Коэфф. сетки a/W</span><input type="range" min={1} max={2} step={0.05} value={spacing} onChange={(e) => setSpacing(Number(e.target.value))} /><b>{spacing.toFixed(2)}</b></label>
                <label className="slider-row"><span>Коэфф. разбуривания</span><input type="range" min={1} max={1.15} step={0.01} value={oversizeCoeff} onChange={(e) => setOversizeCoeff(Number(e.target.value))} /><b>{oversizeCoeff.toFixed(2)}</b></label>
              </div>
            </fieldset>
          </div>
        </section>

        <section className="panel variants-panel">
          <header>
            <b>Варианты сетки</b>
            <div className="panel-header-actions">
              <button
                type="button"
                className="secondary-button"
                disabled={!ready}
                aria-describedby={kuzramCaption ? "kuzram-caption" : undefined}
                onClick={() => setKuzramOpen(true)}
              >
                Модель Kuz-Ram
              </button>
              {kuzramCaption && (
                <span id="kuzram-caption" className="kuzram-caption" title={`Настройки модели: ${kuzramCaption}`}>
                  {kuzramCaption}
                </span>
              )}
              {/* Живая область есть всегда, пустая без пометки: так программы
                  чтения экрана объявляют её появление. Пояснение — и в title,
                  и скрытым текстом, чтобы его слышали без мыши. */}
              <span
                className="kuzram-outdated"
                role="status"
                title={kuzramOutdatedHint ? `Варианты посчитаны по прежним настройкам модели: ${kuzramOutdatedHint}` : undefined}
              >
                {kuzramOutdatedHint && (
                  <>
                    варианты — по прежним настройкам модели
                    <span className="sr-only">: {kuzramOutdatedHint}</span>
                  </>
                )}
              </span>
              {onSendToDesign && (
                <button className="secondary-button" disabled={!selected} onClick={() => selected && onSendToDesign(selected)}>
                  Перенести в проект →
                </button>
              )}
            </div>
          </header>
          <div className="variants-metrics"><MetricChips metrics={metrics} /></div>
          <div className="variants-body">
            <div className="table-scroll">
              <table>
                <thead><tr><th aria-label="Выбор" /><th>Коронка, мм</th><th>Сетка a × b, м</th><th className="num">q</th><th className="num">Негаб.</th></tr></thead>
                <tbody>
                  {variants.map((item, index) => (
                    <tr key={item.crown_mm} className={index === selectedIndex ? "selected" : ""} onClick={() => setSelectedIndex(index)}>
                      <td><span className="row-radio" /></td>
                      <td><b>Ø {item.crown_mm}</b></td>
                      <td>{item.grid_label}</td>
                      <td className="num">
                        {!item.reached && <ThresholdFlag />}
                        {formatQ(item.specific_q_kg_m3, ".")}
                      </td>
                      <td className="num">
                        {formatOversize(item.oversize_pct, item.reached, variantsThresholdPct ?? threshold, 1, ".")}%
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {!variants.length && <p className="table-empty">Нет расчёта</p>}
            </div>
            <div className="variants-chart">
              <p className="block-caption">q от диаметра</p>
              <ResultsChart variants={variants} size="compact" />
            </div>
          </div>
        </section>

        <PassportBar
          variants={[
            { key: "left", label: "Вариант 1", geometry: leftGeometry.geometry, pending: leftGeometry.loading },
            { key: "right", label: "Вариант 2", geometry: rightGeometry.geometry, pending: rightGeometry.loading },
          ]}
          objectName={objectName}
          onOpenEconomics={onOpenEconomics}
        />
      </div>

      {selected && rock ? (
        <ChargeComparison
          cardKey={objectName}
          variants={[
            {
              key: "left",
              label: "Вариант 1",
              shortLabel: "Вар. 1",
              color: variantColor(panelInputs.left),
              initialInputs: panelInputs.left,
              onInputsChange: handleLeftInputs,
              geometry: leftGeometry.geometry,
              error: leftGeometry.error,
              loading: leftGeometry.loading,
            },
            {
              key: "right",
              label: "Вариант 2",
              shortLabel: "Вар. 2",
              color: variantColor(panelInputs.right),
              initialInputs: panelInputs.right,
              onInputsChange: handleRightInputs,
              geometry: rightGeometry.geometry,
              error: rightGeometry.error,
              loading: rightGeometry.loading,
            },
          ]}
          crownMm={selected.crown_mm}
          gridLabel={selected.grid_label}
          depthM={benchHeight + overdrill}
          explosives={explosives}
          nsiLengthOptions={nsiLengthOptions}
          detonatorDelayOptions={detonatorDelayOptions}
          blockVolumeM3={blockVolumeM3}
          onBlockVolumeChange={setBlockVolumeM3}
          additionalHolesPct={additionalHolesPct}
          onAdditionalHolesChange={setAdditionalHolesPct}
        />
      ) : (
        <section className="panel charge-comparison charge-comparison-empty">
          <header><b>Схема заряда и сравнение вариантов</b></header>
          <p className="page-caption">После расчёта вариантов сетки здесь появятся два варианта заряда и их сравнение.</p>
        </section>
      )}

      <KuzRamDialog
        open={kuzramOpen}
        onClose={() => setKuzramOpen(false)}
        block={kuzram}
        onSettingsChange={setKuzramSettings}
        source={kuzramSource}
        busy={kuzramBusy}
        outdatedHint={kuzramOutdatedHint}
        error={optimizeErrorMessage}
        variants={variants}
        selectedIndex={selectedIndex}
        onSelect={setSelectedIndex}
        thresholdPct={variantsThresholdPct ?? threshold}
        onFactsChange={setKuzramFacts}
        onCalibrate={calibrateKuzram}
      />
    </div>
  );
}

export function CalcPage({
  onSendToDesign,
  onOpenEconomics,
}: {
  onSendToDesign?: (variant: BlastVariant) => void;
  onOpenEconomics?: (passportId: string) => void;
}) {
  return <FullBvrCalc onSendToDesign={onSendToDesign} onOpenEconomics={onOpenEconomics} />;
}
