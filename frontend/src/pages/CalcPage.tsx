import { useEffect, useMemo, useState } from "react";
import { api } from "../api/endpoints";
import { useWorkspace } from "../app/useWorkspace";
import { DataTable } from "../components/DataTable";
import { DrillingGeometryPage } from "./calc/DrillingGeometryPage";
import { HolePanel } from "./calc/HolePanel";
import { ManualScenarioPage } from "./calc/ManualScenarioPage";
import type { BlastGeometryResponse, BlastVariant, Explosive, Rock } from "../types";
import type { TechnicalPassport } from "../types/blockEconomics";

const DEFAULT_EXPLOSIVE_1 = "ПВВ Гранулит-РП";
const DEFAULT_EXPLOSIVE_2 = "ПЭВВ ЭВЕРСИН Э-100";

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

/**
 * Технические паспорта блока: вход во вкладку «Экономика».
 *
 * Паспорт фиксирует рассчитанный блок и ревизию справочников, поэтому
 * экономика считается по нему, а не по текущему состоянию формы.
 */
function PassportBar({
  geometry,
  onOpenEconomics,
}: {
  geometry: BlastGeometryResponse | null;
  onOpenEconomics?: (passportId: string) => void;
}) {
  const [passports, setPassports] = useState<TechnicalPassport[]>([]);
  const [sites, setSites] = useState<{ code: string; name: string }[]>([]);
  const [siteCode, setSiteCode] = useState("");
  const [objectName, setObjectName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    Promise.all([api.economics.technicalPassports(), api.economics.referenceSnapshot()])
      .then(([saved, snapshot]) => {
        setPassports(saved);
        const siteItems = (snapshot.sections.sites ?? []).map((item) => ({
          code: item.code,
          name: item.name,
        }));
        setSites(siteItems);
        setSiteCode((current) => current || siteItems[0]?.code || "");
      })
      .catch((reason) =>
        setError(reason instanceof Error ? reason.message : "Не удалось загрузить паспорта."),
      );
  }, []);

  async function savePassport() {
    if (!geometry || !siteCode) return;
    setBusy(true);
    setError("");
    try {
      const created = await api.economics.createTechnicalPassport({
        site_code: siteCode,
        object_name: objectName.trim() || `Блок ${Math.round(geometry.block.block_volume_m3)} м³`,
        block: geometry.block as unknown as Record<string, unknown>,
        selected_variant: { label: geometry.label },
      });
      setPassports((rows) => [created, ...rows]);
      setObjectName("");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Не удалось сохранить паспорт.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="panel passport-bar">
      <header><b>Технические паспорта</b><span>Экономика блока</span></header>
      <div className="panel-body">
        {error && <div className="page-error" role="alert">{error}</div>}
        <div className="economic-fields-grid">
          <label>
            Объект работ
            <select value={siteCode} onChange={(event) => setSiteCode(event.target.value)}>
              {sites.map((site) => <option key={site.code} value={site.code}>{site.name}</option>)}
            </select>
          </label>
          <label>
            Название паспорта
            <input
              value={objectName}
              placeholder="Блок, м³"
              onChange={(event) => setObjectName(event.target.value)}
            />
          </label>
          <div className="button-row">
            <button type="button" onClick={() => void savePassport()} disabled={busy || !geometry || !siteCode}>
              Сохранить паспорт
            </button>
          </div>
        </div>
        {geometry && (
          // В паспорт уходит блок «Варианта 1» с его зарядом и недозарядом —
          // показываем это до сохранения, чтобы масса не была сюрпризом.
          <p className="page-caption">
            В паспорт пойдёт «{geometry.label}»: {Math.round(geometry.block.total_charge_mass_kg).toLocaleString("ru-RU")} кг ВВ,{" "}
            {geometry.block.total_holes} скважин, {Math.round(geometry.block.drilling_footage_m).toLocaleString("ru-RU")} п.м.,{" "}
            {geometry.block.specific_q_kg_m3.toFixed(2)} кг/м³ с доп. скважинами. Кнопка «Экономика» открывает сохранённый
            паспорт: чтобы передать текущий расчёт, сначала сохраните новый.
          </p>
        )}
        {passports.length === 0 ? (
          <p className="page-caption">Сохранённых паспортов нет.</p>
        ) : (
          <div className="passport-list">
            {passports.slice(0, 8).map((passport) => (
              <div className="passport-list-row" key={passport.id}>
                <span>
                  <b>{passport.object_name}</b>
                  <small>
                    {sites.find((site) => site.code === passport.site_code)?.name ?? passport.site_code} · вер.{" "}
                    {passport.version_no} · {new Date(passport.created_at).toLocaleDateString("ru-RU")} ·{" "}
                    {Math.round(Number(passport.physical.explosive_kg ?? 0)).toLocaleString("ru-RU")} кг ВВ
                  </small>
                </span>
                <em>{Number(passport.physical.rock_volume_m3 ?? 0).toLocaleString("ru-RU")} м³</em>
                <button
                  type="button"
                  className="secondary-button"
                  onClick={() => onOpenEconomics?.(passport.id)}
                  disabled={!onOpenEconomics}
                >
                  Экономика
                </button>
              </div>
            ))}
          </div>
        )}
      </div>
    </section>
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
  const [rockName, setRockName] = useState("");
  const [explosiveKey, setExplosiveKey] = useState("");
  const [lumpSize, setLumpSize] = useState(400);
  const [benchHeight, setBenchHeight] = useState(10);
  const [overdrill, setOverdrill] = useState(1);
  const [oversizeCoeff, setOversizeCoeff] = useState(1.05);
  const [spacing, setSpacing] = useState(1.25);
  const [threshold, setThreshold] = useState(5);
  const [allCrowns, setAllCrowns] = useState<number[]>([]);
  const [selectedCrowns, setSelectedCrowns] = useState<number[]>([]);
  const [nsiLengthOptions, setNsiLengthOptions] = useState<number[]>([12]);
  const [detonatorDelayOptions, setDetonatorDelayOptions] = useState<number[]>([500]);
  const [variants, setVariants] = useState<BlastVariant[]>([]);
  const [selectedIndex, setSelectedIndex] = useState(0);
  const [blockVolumeM3, setBlockVolumeM3] = useState(30_000);
  const [additionalHolesPct, setAdditionalHolesPct] = useState(3.0);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [geometry, setGeometry] = useState<BlastGeometryResponse | null>(null);

  useEffect(() => {
    Promise.all([api.rocks(), api.explosives(), api.blastOptions()]).then(([rockData, explosiveData, opts]) => {
      setRocks(rockData.items);
      setExplosives(explosiveData.items);
      setRockName(rockData.default_name);
      setExplosiveKey(explosiveData.default_key);
      setAllCrowns(opts.crown_diameters_mm);
      setSelectedCrowns(opts.crown_diameters_mm);
      setNsiLengthOptions(opts.nsi_length_options_m);
      setDetonatorDelayOptions(opts.detonator_delay_ms_options);
    }).catch((reason) => setError(reason instanceof Error ? reason.message : "Не удалось загрузить справочники."));
  }, []);

  const rock = useMemo(() => rocks.find((r) => r.name === rockName), [rocks, rockName]);
  const explosive = useMemo(() => explosives.find((e) => e.key === explosiveKey), [explosives, explosiveKey]);
  const selected = variants[selectedIndex];

  function toggleCrown(value: number) {
    setSelectedCrowns((prev) => (prev.includes(value) ? prev.filter((c) => c !== value) : [...prev, value].sort((a, b) => a - b)));
  }

  async function calculate() {
    if (!rock || !explosive || !selectedCrowns.length) return;
    setBusy(true);
    setError("");
    try {
      const result = await api.optimize({
        rock, explosive, lumpSize, benchHeight, overdrill, oversizeCoeff, spacing, threshold, crownDiametersMm: selectedCrowns,
      });
      setVariants(result.variants);
      const preferred = result.variants.findIndex((v) => v.crown_mm === 152);
      setSelectedIndex(preferred >= 0 ? preferred : 0);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Ошибка расчёта.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="page-content">
      {error && <div className="page-error" role="alert">{error}</div>}
      <div className="calculator-grid">
        <section className="panel input-panel">
          <header><b>Исходные данные</b><span>01</span></header>
          <div className="panel-body">
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
            <button className="calculate-button" onClick={calculate} disabled={busy || !rock || !explosive || !selectedCrowns.length}>
              {busy ? "Выполняется расчёт…" : "Рассчитать варианты"}
            </button>
          </div>
        </section>
        <div className="results-column">
          <div className="metrics-grid">
            <div><span>Удельный расход</span><strong>{selected ? selected.specific_q_kg_m3.toFixed(2) : "—"}</strong><small>{explosiveBasis === "per_m" ? "кг/п.м." : "кг/м³"}</small></div>
            <div><span>ЛНС W</span><strong>{selected ? selected.line_of_least_resistance_m.toFixed(2) : "—"}</strong><small>м</small></div>
            <div><span>Средний кусок x50</span><strong>{selected ? selected.x50_mm.toFixed(1) : "—"}</strong><small>мм</small></div>
            <div><span>Негабарит</span><strong>{selected ? selected.oversize_pct.toFixed(1) : "—"}</strong><small>%</small></div>
          </div>
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
              defaultUnderchargeM={3.1}
              showChargeDesign={true}
              explosiveBasis={explosiveBasis}
              nsiLengthOptions={nsiLengthOptions}
              detonatorDelayOptions={detonatorDelayOptions}
              onGeometry={setGeometry}
            />
            <HolePanel
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
              defaultUnderchargeM={2.0}
              showChargeDesign={true}
              explosiveBasis={explosiveBasis}
              isBlastContextSource={false}
              nsiLengthOptions={nsiLengthOptions}
              detonatorDelayOptions={detonatorDelayOptions}
            />
          </div>
          <PassportBar geometry={geometry} onOpenEconomics={onOpenEconomics} />
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
  const { activeScenario, loading } = useWorkspace();
  if (loading) return <div className="page-content">Загрузка…</div>;
  if (!activeScenario) return <div className="page-content">Выберите сценарий.</div>;

  const profile = activeScenario.calc_profile;
  return (
    <div className="page-content-wrap">
      <p className="page-caption">{profile.ui_caption}</p>
      {profile.is_manual_input ? (
        <ManualScenarioPage profile={profile} />
      ) : profile.mode === "drilling_geometry" ? (
        <DrillingGeometryPage />
      ) : (
        <FullBvrCalc
          explosiveBasis={profile.explosive_basis === "per_m" ? "per_m" : "per_m3"}
          onSendToDesign={onSendToDesign}
          onOpenEconomics={onOpenEconomics}
        />
      )}
    </div>
  );
}
