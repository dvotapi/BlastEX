import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { api } from "../api/endpoints";
import { useWorkspace } from "../app/useWorkspace";
import { useTopbarSlot } from "../app/topbarSlot";
import { DataTable } from "../components/DataTable";
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
import { CalcTopStrip, CalcWorkspaceNotices } from "./calc/CalcTopStrip";
import { PassportBar } from "./calc/PassportBar";
import { HolePanel } from "./calc/HolePanel";
import { useCalcInputsAutosave } from "./calc/useCalcInputsAutosave";
import type { BlastGeometryResponse, BlastVariant, Explosive, Rock } from "../types";

function ResultsChart({ variants }: { variants: BlastVariant[] }) {
  if (!variants.length) return <div className="chart-empty">После расчёта здесь появится сравнение вариантов.</div>;
  const width = 620;
  const height = 190;
  const pad = { left: 42, right: 20, top: 20, bottom: 35 };
  const qValues = variants.map((item) => item.specific_q_kg_m3);
  const minQ = Math.min(...qValues) - 0.04;
  const maxQ = Math.max(...qValues) + 0.04;
  const x = (index: number) => pad.left + index * ((width - pad.left - pad.right) / Math.max(1, variants.length - 1));
  const y = (value: number) => pad.top + ((maxQ - value) / (maxQ - minQ)) * (height - pad.top - pad.bottom);
  const points = variants.map((item, index) => `${x(index)},${y(item.specific_q_kg_m3)}`).join(" ");
  const tickCount = 4;
  const ticks = Array.from({ length: tickCount + 1 }, (_, i) => minQ + ((maxQ - minQ) * i) / tickCount);
  return (
    <svg className="result-chart" viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Зависимость удельного расхода от диаметра коронки">
      {ticks.map((value) => (
        <line key={value} className="grid-line" x1={pad.left} x2={width - pad.right} y1={y(value)} y2={y(value)} />
      ))}
      <line className="axis-line" x1={pad.left} x2={pad.left} y1={pad.top} y2={height - pad.bottom} />
      {ticks.map((value) => (
        <g key={value}>
          <line className="axis-tick" x1={pad.left - 4} x2={pad.left} y1={y(value)} y2={y(value)} />
          <text className="axis-label" x={pad.left - 8} y={y(value)} textAnchor="end" dominantBaseline="middle">{value.toFixed(2)}</text>
        </g>
      ))}
      <polyline points={points} />
      {variants.map((item, index) => <g key={item.crown_mm}><circle cx={x(index)} cy={y(item.specific_q_kg_m3)} r="5" /><text x={x(index)} y={height - 10} textAnchor="middle">{item.crown_mm}</text></g>)}
    </svg>
  );
}

function FullBvrCalc({
  explosiveBasis,
  onSendToDesign,
  onOpenEconomics,
}: {
  explosiveBasis: "per_m3" | "per_m";
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
  // негабарита, выбранные коронки) — включая применение загруженного листа.
  // Ответ расчёта, запущенного на одном значении счётчика, отбрасывается,
  // если к моменту ответа счётчик уже другой: лист успели поправить, пока
  // ответ летел, и метрики в ответе — уже про прежние значения полей.
  const optimizeGenerationRef = useRef(0);
  const bumpOptimizeGeneration = useCallback(() => {
    optimizeGenerationRef.current += 1;
  }, []);
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
  const [nsiLengthOptions, setNsiLengthOptions] = useState<number[]>([12]);
  const [detonatorDelayOptions, setDetonatorDelayOptions] = useState<number[]>([500]);
  const [variants, setVariants] = useState<BlastVariant[]>([]);
  const [selectedIndex, setSelectedIndex] = useState(0);
  const [blockVolumeM3, setBlockVolumeM3] = useState(30_000);
  const [additionalHolesPct, setAdditionalHolesPct] = useState(3.0);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  // Поля панелей «Вариант 1/2»: панели ведут их у себя, а сюда сообщают об
  // изменениях — из них собираются настройки листа.
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
  // Блоки обеих панелей: в паспорт уходит та, что выбрана под расчётом.
  const [geometries, setGeometries] = useState<Record<string, BlastGeometryResponse | null>>({});
  const geometryFor = (key: string) => (geometry: BlastGeometryResponse) =>
    setGeometries((current) => ({ ...current, [key]: geometry }));

  const {
    state,
    setActiveWorkObjectName,
    error: workspaceError,
    loading: workspaceLoading,
  } = useWorkspace();
  const objectName = state?.settings.active_work_object_name ?? "";
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
    }).catch((reason) => setError(reason instanceof Error ? reason.message : "Не удалось загрузить справочники."));
  }, []);

  const rock = useMemo(() => rocks.find((r) => r.name === rockName), [rocks, rockName]);
  const explosive = useMemo(() => explosives.find((e) => e.key === explosiveKey), [explosives, explosiveKey]);
  const selected = variants[selectedIndex];

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
      panels: panelInputs,
    }),
    [rockName, explosiveKey, lumpSize, benchHeight, overdrill, oversizeCoeff, spacing, threshold,
      selectedCrowns, selected, loadedCrownMm, blockVolumeM3, additionalHolesPct, panelInputs]
  );
  const sheetInputs = useMemo(() => collectCalcInputs(sheet), [sheet]);

  // Статус автосохранения показывает верхняя полоса листа (задача 5).
  const { status: autosaveStatus, flush } = useCalcInputsAutosave({ objectName, inputs: sheetInputs, ready });

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
    setPanelInputs(next.panels);
  }, []);

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
   * `preferredCrownMm` — сохранённый диаметр, если такой вариант найдётся.
   * `isStale` — автозапуск для объекта, который успели сменить: его результат
   * выбрасываем, иначе он затрёт варианты нового объекта. */
  async function runOptimize(
    source: SheetState,
    preferredCrownMm: number | null,
    isStale: () => boolean = () => false,
  ) {
    const sheetRock = rocks.find((r) => r.name === source.rockName);
    const sheetExplosive = explosives.find((e) => e.key === source.explosiveKey);
    if (!sheetRock || !sheetExplosive || !source.selectedCrownsMm.length) return;
    setBusy(true);
    setError("");
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
      });
      if (isStale()) return;
      setVariants(result.variants);
      const restored = preferredCrownMm === null ? -1 : result.variants.findIndex((v) => v.crown_mm === preferredCrownMm);
      const preferred = result.variants.findIndex((v) => v.crown_mm === 152);
      setSelectedIndex(restored >= 0 ? restored : preferred >= 0 ? preferred : 0);
    } catch (reason) {
      if (isStale()) return;
      setError(reason instanceof Error ? reason.message : "Ошибка расчёта.");
    } finally {
      setBusy(false);
    }
  }

  /** Ручной запуск расчёта: если пользователь успел сменить объект или
   * поправить влияющее на расчёт поле, пока ответ ещё летел, результат —
   * уже не про текущий лист, и его нужно отбросить (как и автозапуск после
   * загрузки настроек — `isStale` в `runOptimize`). */
  async function calculate() {
    const requestedObjectName = objectName;
    const startedGeneration = optimizeGenerationRef.current;
    await runOptimize(sheet, null, () =>
      isOptimizationResultStale(
        startedGeneration,
        optimizeGenerationRef.current,
        requestedObjectName,
        objectNameRef.current,
      ),
    );
  }

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
    setLoadedObjectName(null);
    setLoadedCrownMm(null);
    setVariants([]);
    setGeometries({});
    void (async () => {
      await flush();
      try {
        const saved = await api.calcInputs(objectName);
        if (cancelled) return;
        const applied = applyCalcInputs(saved.inputs, catalogs);
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
          await runOptimize(applied, applied.selectedCrownMm, () =>
            cancelled ||
            isOptimizationResultStale(startedGeneration, optimizeGenerationRef.current, objectName, objectNameRef.current),
          );
        } else {
          applySheet(defaultCalcSheet(catalogs, referenceDefaults));
          if (cancelled) return;
          setLoadedObjectName(objectName);
        }
      } catch {
        if (cancelled) return;
        // Настройки не прочитались: значения прошлого объекта на листе были бы
        // чужими, поэтому открываем умолчания. `loadedObjectName` не ставим —
        // лист остаётся «не готовым», и автосохранение не затрёт умолчаниями
        // то, что мы не смогли прочитать.
        applySheet(defaultCalcSheet(catalogs, referenceDefaults));
        setError(
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
      teamName={state?.settings.team_name ?? ""}
      objectName={objectName}
      objects={state?.references.work_object_records ?? []}
      onObjectChange={(name) => void setActiveWorkObjectName(name)}
      autosaveStatus={autosaveStatus}
      metrics={{
        q: selected ? selected.specific_q_kg_m3 : null,
        w: selected ? selected.line_of_least_resistance_m : null,
        x50: selected ? selected.x50_mm : null,
        oversize: selected ? selected.oversize_pct : null,
      }}
      workspaceLoading={workspaceLoading}
    />
  );

  return (
    <div className="page-content">
      {error && <div className="page-error" role="alert">{error}</div>}
      <CalcWorkspaceNotices workspaceError={workspaceError} warnings={state?.warnings ?? []} />
      {topbarSlot ? createPortal(topStrip, topbarSlot) : topStrip}
      <div className="calculator-grid">
        <section className="panel input-panel">
          <header><b>Исходные данные</b><span>01</span></header>
          <div className="panel-body">
            {/* Пока настройки объекта не загружены (`!ready`), правка любого
                поля пропала бы: `applySheet` при ответе перезапишет её своими
                значениями. Отключаем весь ввод на этот момент — `fieldset`
                выключает вложенные поля браузерными средствами, `display:
                contents` не мешает сетке `.panel-body`. */}
            <fieldset className="input-panel-fieldset" disabled={!ready}>
              <label>Порода<select value={rockName} onChange={(e) => setRockName(e.target.value)}>{rocks.map((r) => <option key={r.id || r.name}>{r.name}</option>)}</select></label>
              <label>Взрывчатое вещество<select value={explosiveKey} onChange={(e) => setExplosiveKey(e.target.value)}>{explosives.map((ex) => <option key={ex.id || ex.key} value={ex.key}>{ex.name}</option>)}</select></label>
              <div className="field-pair">
                <label>Высота уступа, м<input type="number" min={5} max={25} step={0.5} value={benchHeight} onChange={(e) => setBenchHeight(Number(e.target.value))} /></label>
                <label>Перебур, м<input type="number" min={0} max={3} step={0.1} value={overdrill} onChange={(e) => setOverdrill(Number(e.target.value))} /></label>
              </div>
              <label>Кондиционный кусок, мм<input type="number" min={100} max={1200} step={50} value={lumpSize} onChange={(e) => setLumpSize(Number(e.target.value))} /></label>
              <label className="range-label"><span>Допустимый негабарит <b>{threshold}%</b></span><input type="range" min={1} max={15} step={0.5} value={threshold} onChange={(e) => setThreshold(Number(e.target.value))} /></label>
              <label className="range-label"><span>Коэффициент сетки a/W <b>{spacing.toFixed(2)}</b></span><input type="range" min={1} max={2} step={0.05} value={spacing} onChange={(e) => setSpacing(Number(e.target.value))} /></label>
              <label className="range-label"><span>Коэфф. разбуривания <b>{oversizeCoeff.toFixed(2)}</b></span><input type="range" min={1} max={1.15} step={0.01} value={oversizeCoeff} onChange={(e) => setOversizeCoeff(Number(e.target.value))} /></label>
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
            </fieldset>
          </div>
        </section>
        <div className="results-column">
          <section className="panel"><header><b>Зависимость расхода от диаметра</b><span>Куз–Рам</span></header><ResultsChart variants={variants} /></section>
          <section className="panel variants-panel"><header><b>Варианты сетки</b><span>{variants.length ? `${variants.length} вариантов` : "Нет расчёта"}</span></header>
            <div className="table-scroll"><table><thead><tr><th></th><th>Коронка</th><th>Сетка a × b</th><th>q</th><th>Негабарит</th></tr></thead><tbody>
              {variants.map((item, index) => <tr key={item.crown_mm} className={index === selectedIndex ? "selected" : ""} onClick={() => setSelectedIndex(index)}><td><span className="row-radio" /></td><td><b>Ø {item.crown_mm} мм</b></td><td>{item.grid_label} м</td><td>{item.specific_q_kg_m3.toFixed(2)}</td><td>{item.oversize_pct.toFixed(1)}%</td></tr>)}
            </tbody></table></div>
            {selected && onSendToDesign && (
              <div className="panel-body" style={{ borderTop: "1px solid var(--line, #d7e0db)", paddingTop: 12 }}>
                <button className="secondary-button" onClick={() => onSendToDesign(selected)}>Перенести в проект →</button>
              </div>
            )}
          </section>
        </div>
      </div>

      {selected && rock && (
        <div className="hole-visualization">
          <h2>{explosiveBasis === "per_m" ? "Схема заряда контура" : "Схема заряда скважины"}</h2>
          <div className="calc-inputs-grid">
            <label>Объём блока, м³<input type="number" min={1000} step={1000} value={blockVolumeM3} onChange={(e) => setBlockVolumeM3(Number(e.target.value))} /></label>
            <label>Доп. скважины, %<input type="number" min={0} max={20} step={0.5} value={additionalHolesPct} onChange={(e) => setAdditionalHolesPct(Number(e.target.value))} /></label>
          </div>
          <div className="hole-panels-row">
            <HolePanel
              key={`${objectName}-left`}
              panelKey="left"
              variantLabel="Вариант 1"
              gridAM={selected.grid_a_m}
              gridBM={selected.grid_b_m}
              depthM={benchHeight + overdrill}
              overdrillM={overdrill}
              crownMm={selected.crown_mm}
              holeOversizeCoeff={oversizeCoeff}
              blockVolumeM3={blockVolumeM3}
              additionalHolesPct={additionalHolesPct / 100}
              defaultExplosiveKey={DEFAULT_EXPLOSIVE_1}
              defaultUnderchargeM={DEFAULT_UNDERCHARGE_1_M}
              showChargeDesign={true}
              explosiveBasis={explosiveBasis}
              nsiLengthOptions={nsiLengthOptions}
              detonatorDelayOptions={detonatorDelayOptions}
              initialInputs={panelInputs.left}
              onInputsChange={handleLeftInputs}
              onGeometry={geometryFor("left")}
            />
            <HolePanel
              key={`${objectName}-right`}
              panelKey="right"
              variantLabel="Вариант 2"
              gridAM={selected.grid_a_m}
              gridBM={selected.grid_b_m}
              depthM={benchHeight + overdrill}
              overdrillM={overdrill}
              crownMm={selected.crown_mm}
              holeOversizeCoeff={oversizeCoeff}
              blockVolumeM3={blockVolumeM3}
              additionalHolesPct={additionalHolesPct / 100}
              defaultExplosiveKey={DEFAULT_EXPLOSIVE_2}
              defaultUnderchargeM={DEFAULT_UNDERCHARGE_2_M}
              showChargeDesign={true}
              explosiveBasis={explosiveBasis}
              isBlastContextSource={false}
              nsiLengthOptions={nsiLengthOptions}
              detonatorDelayOptions={detonatorDelayOptions}
              initialInputs={panelInputs.right}
              onInputsChange={handleRightInputs}
              onGeometry={geometryFor("right")}
            />
          </div>
          <PassportBar
            variants={[
              { key: "left", label: "Вариант 1", geometry: geometries.left ?? null },
              { key: "right", label: "Вариант 2", geometry: geometries.right ?? null },
            ]}
            objectName={objectName}
            onOpenEconomics={onOpenEconomics}
          />
        </div>
      )}
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
  return (
    <div className="page-content-wrap">
      <p className="page-caption">Комплекс БВР: оптимизация q, сетка, схема заряда</p>
      <FullBvrCalc
        explosiveBasis="per_m3"
        onSendToDesign={onSendToDesign}
        onOpenEconomics={onOpenEconomics}
      />
    </div>
  );
}
