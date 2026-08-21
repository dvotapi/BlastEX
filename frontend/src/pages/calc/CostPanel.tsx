import { useEffect, useMemo, useState } from "react";
import { api } from "../../api/endpoints";
import { activeModules, buildCostContext } from "../../app/costContext";
import { useWorkspace } from "../../app/useWorkspace";
import { DataTable } from "../../components/DataTable";
import type {
  AggregatedCostResult,
  BlockGeometry,
  CatalogItem,
  HoleGeometry,
  InitiationConfig,
  MaterialsSelection,
} from "../../types";

const SECTION_ORDER: [string, string][] = [
  ["2.1", "Хранение, производство и доставка ВМ и СИ"],
  ["2.2", "Суточные, вахтовые, проживание"],
  ["2.3", "Фонд оплаты труда"],
  ["2.4", "ГСМ на бурение"],
  ["2.5", "Амортизация"],
  ["2.6", "Общепроизводственные затраты"],
];

function byCategory(catalog: CatalogItem[], category: string) {
  return catalog.filter((item) => item.category === category);
}

function money(n: number) {
  return n.toLocaleString("ru-RU", { maximumFractionDigits: 0 });
}

export type BlockDataOverride = {
  hole: HoleGeometry;
  block: BlockGeometry;
  initiation: InitiationConfig;
  explosiveKey: string;
  holeDepthM: number;
  productionVolumeTons?: number;
};

export function CostPanel({
  panelKey,
  variantTitle,
  explosiveKey,
  hole,
  block,
  initiation,
  holeDepthM,
  blockDataOverride,
}: {
  panelKey: string;
  variantTitle: string;
  explosiveKey: string;
  hole: HoleGeometry;
  block: BlockGeometry;
  initiation: InitiationConfig;
  holeDepthM: number;
  blockDataOverride?: BlockDataOverride;
}) {
  const { state, activeScenario, setBlastContext } = useWorkspace();
  const overrides = state?.snapshot.scenario_phase_overrides ?? {};
  const modules = useMemo(() => activeModules(activeScenario, overrides), [activeScenario, overrides]);
  const showMaterials = modules.has("materials");
  const showDrilling = modules.has("drilling");
  const showFixed = modules.has("fixed");
  const showManufacturing = modules.has("manufacturing");
  const showLabor = modules.has("labor");

  const [productionTons, setProductionTons] = useState(100);
  const [selection, setSelection] = useState<MaterialsSelection | null>(null);
  const [result, setResult] = useState<AggregatedCostResult | null>(null);
  const [error, setError] = useState("");

  const catalog = state?.snapshot.cost_catalog_records ?? [];
  const explosives = byCategory(catalog, "explosive");
  const detonators = byCategory(catalog, "detonator");
  const downholeNsi = byCategory(catalog, "downhole_nsi");
  const surfaceNsi = byCategory(catalog, "surface_nsi");
  const startNsi = byCategory(catalog, "start_nsi");

  const effHole = blockDataOverride?.hole ?? hole;
  const effBlock = blockDataOverride?.block ?? block;
  const effInitiation = blockDataOverride?.initiation ?? initiation;
  const effExplosiveKey = blockDataOverride?.explosiveKey || explosiveKey;
  const effHoleDepthM = blockDataOverride?.holeDepthM ?? holeDepthM;

  useEffect(() => {
    if (!showMaterials || !catalog.length) return;
    let cancelled = false;
    api.materialsAuto(effExplosiveKey, effInitiation).then((res) => {
      if (!cancelled) setSelection(res.selection);
    }).catch(() => undefined);
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [showMaterials, effExplosiveKey, effInitiation.nsi_per_hole, effInitiation.nsi_length_1_m, effInitiation.nsi_length_2_m, catalog.length]);

  useEffect(() => {
    if (effBlock.block_volume_m3 > 0) {
      setBlastContext({
        blockVolumeM3: effBlock.block_volume_m3,
        additionalHolesPct: effBlock.additional_holes_pct,
        drillingFootageM: effBlock.drilling_footage_m,
        totalHoles: effBlock.total_holes,
        crownMm: effHole.charge_diameter_m ? (effHole.charge_diameter_m * 1000) / 1.05 : 0,
      });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [effBlock.block_volume_m3, effBlock.total_holes]);

  useEffect(() => {
    if (!state || !activeScenario) return;
    const controller = { cancelled: false };
    (async () => {
      try {
        const payload: Record<string, unknown> = {
          scenario_id: activeScenario.id,
          work_object_name: state.settings.active_work_object_name,
          context: buildCostContext(state),
          materials_selection: showMaterials ? selection : null,
          production_volume_tons: showManufacturing ? productionTons : 0,
        };
        if (activeScenario.calc_profile.is_manual_input) {
          payload.manual_input = {
            block_volume_m3: effBlock.block_volume_m3,
            total_holes: effBlock.total_holes,
            drilling_footage_m: effBlock.drilling_footage_m,
            total_charge_mass_kg: effBlock.total_charge_mass_kg,
            production_volume_tons: showManufacturing ? productionTons : 0,
            explosive_key: effExplosiveKey,
          };
        } else {
          payload.block = {
            hole: effHole,
            block: effBlock,
            initiation: effInitiation,
            explosive_key: effExplosiveKey,
            hole_depth_m: effHoleDepthM,
            materials_selection: showMaterials ? selection : null,
            production_volume_tons: showManufacturing ? productionTons : 0,
          };
        }
        const res = await api.calculateCost(payload);
        if (!controller.cancelled) { setResult(res); setError(""); }
      } catch (reason) {
        if (!controller.cancelled) setError(reason instanceof Error ? reason.message : "Ошибка расчёта сметы.");
      }
    })();
    return () => { controller.cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    state, activeScenario, selection, productionTons, showManufacturing, showMaterials,
    effHole.charge_mass_kg, effBlock.total_holes, effBlock.block_volume_m3, effExplosiveKey, effHoleDepthM,
  ]);

  if (!activeScenario) return null;

  const vol = effBlock.block_volume_m3 > 0 ? effBlock.block_volume_m3 : 1;

  return (
    <div className="cost-panel" data-panel={panelKey}>
      <h4>Смета затрат — сценарий «{activeScenario.name}»</h4>
      {state?.settings.active_work_object_name && (
        <p className="cost-caption">Объект работ: <b>{state.settings.active_work_object_name}</b> (мобилизация и цена ДТ учитываются в бурении).</p>
      )}
      {error && <div className="page-error">{error}</div>}

      {showManufacturing && (
        <label className="field-inline">Объём производства ЭВВ, т
          <input type="number" min={0} step={10} value={productionTons} onChange={(e) => setProductionTons(Number(e.target.value))} />
        </label>
      )}

      {showMaterials && catalog.length > 0 && selection && (
        <div className="materials-selection">
          <h5>1.1 — ВВ, детонаторы, НСИ</h5>
          <div className="field-pair">
            <label>Номенклатура ВВ
              <select value={selection.explosive_id} onChange={(e) => setSelection({ ...selection, explosive_id: e.target.value })}>
                {explosives.map((i) => <option key={i.id} value={i.id}>{i.name}</option>)}
              </select>
            </label>
            <label>Пром. детонатор
              <select value={selection.detonator_id} onChange={(e) => setSelection({ ...selection, detonator_id: e.target.value })}>
                {detonators.map((i) => <option key={i.id} value={i.id}>{i.name}</option>)}
              </select>
            </label>
          </div>
          <div className="field-pair">
            <label>НСИ скважинное
              <select value={selection.downhole_nsi1_id} onChange={(e) => setSelection({ ...selection, downhole_nsi1_id: e.target.value })}>
                {downholeNsi.map((i) => <option key={i.id} value={i.id}>{i.name}</option>)}
              </select>
            </label>
            {effInitiation.nsi_per_hole === 2 && (
              <label>НСИ скважинное (дубль)
                <select value={selection.downhole_nsi2_id ?? ""} onChange={(e) => setSelection({ ...selection, downhole_nsi2_id: e.target.value })}>
                  {downholeNsi.map((i) => <option key={i.id} value={i.id}>{i.name}</option>)}
                </select>
              </label>
            )}
          </div>
          {(surfaceNsi.length > 0 || startNsi.length > 0) && (
            <div className="field-pair">
              {surfaceNsi.length > 0 && (
                <label>НСИ поверхностное
                  <select value={selection.surface_nsi_id} onChange={(e) => setSelection({ ...selection, surface_nsi_id: e.target.value })}>
                    {surfaceNsi.map((i) => <option key={i.id} value={i.id}>{i.name}</option>)}
                  </select>
                </label>
              )}
              {startNsi.length > 0 && (
                <label>НСИ стартовое
                  <select value={selection.start_nsi_id} onChange={(e) => setSelection({ ...selection, start_nsi_id: e.target.value })}>
                    {startNsi.map((i) => <option key={i.id} value={i.id}>{i.name}</option>)}
                  </select>
                </label>
              )}
            </div>
          )}
        </div>
      )}

      {result?.materials_cost && (showMaterials || showManufacturing) && (
        <div className="cost-section">
          <h5>{showManufacturing ? "Материалы производства ЭВВ" : "1.1 — ВВ, детонаторы, НСИ"}</h5>
          <DataTable
            columns={[
              { key: "section", label: "Раздел" },
              { key: "nomenclature", label: "Наименование" },
              { key: "quantity", label: "Кол-во", align: "right", format: (r) => (r.unit === "шт" ? String(Math.round(r.quantity)) : r.quantity.toFixed(2)) },
              { key: "unit", label: "Ед." },
              { key: "amount", label: "Сумма, руб", align: "right", format: (r) => money(r.amount) },
            ]}
            rows={result.materials_cost.lines}
          />
          <p className="cost-caption">Итого: <b>{money(result.materials_cost.total_amount)} руб</b> ({(result.materials_cost.total_amount / vol).toFixed(2)} руб/м³)</p>
        </div>
      )}

      {showDrilling && result?.drilling_total_cost && (
        <div className="cost-section">
          <h5>1.2 — бурение</h5>
          <table className="hole-metrics-table">
            <tbody>
              <tr><td>Скважин, шт.</td><td>{result.drilling_total_cost.total_holes}</td></tr>
              <tr><td>Глубина скважины, м</td><td>{result.drilling_total_cost.hole_depth_m.toFixed(1)}</td></tr>
              <tr><td>Погонаж бурения, п.м.</td><td>{result.drilling_total_cost.drilling_footage_m.toFixed(0)}</td></tr>
              <tr><td>Цена бурения, руб/п.м.</td><td>{result.drilling_total_cost.price_per_m.toFixed(2)}</td></tr>
              <tr><td>Сумма 1.2, руб</td><td>{money(result.drilling_total_cost.amount)}</td></tr>
            </tbody>
          </table>
        </div>
      )}

      {showLabor && result?.labor_fot && (
        <p className="cost-caption"><b>2.3 — ФОТ:</b> {money(result.labor_fot.total_fot)} руб</p>
      )}

      {showFixed && result?.fixed_costs && (
        <div className="cost-section">
          <h5>Постоянные расходы</h5>
          {result.fixed_costs.lines.length ? (
            <>
              <DataTable
                columns={[
                  { key: "section", label: "Раздел", format: (r) => `${r.section} — ${r.section_title}` },
                  { key: "name", label: "Наименование" },
                  { key: "amount", label: "Сумма, руб", align: "right", format: (r) => money(r.amount) },
                ]}
                rows={result.fixed_costs.lines}
              />
              <p className="cost-caption">
                {SECTION_ORDER.filter(([code]) => (result.fixed_costs!.section_totals[code] ?? 0) > 0)
                  .map(([code]) => `${code} ${money(result.fixed_costs!.section_totals[code])} руб`).join(" · ")}
              </p>
              <p className="cost-caption">Итого постоянные: <b>{money(result.fixed_costs.total_amount)} руб</b> ({result.fixed_costs.total_per_m3.toFixed(2)} руб/м³)</p>
            </>
          ) : <p className="cost-caption">Нет активных статей постоянных расходов.</p>}
        </div>
      )}

      {result && (
        <p className="cost-total">
          <b>{variantTitle}</b> — итого: <b>{money(result.total_amount_rub)} руб</b>
          {result.cost_per_m3 > 0 && ` (${result.cost_per_m3.toFixed(2)} руб/м³)`}
          {result.cost_per_ton > 0 && showManufacturing && `, ${result.cost_per_ton.toFixed(2)} руб/т`}
        </p>
      )}

      {result?.child_results && result.child_results.length > 0 && (
        <details className="composite-breakdown">
          <summary>Состав композитного расчёта</summary>
          <ul>
            {result.child_results.map((child, i) => (
              <li key={i}>{child.scenario_id}: переменные {money(child.variable_total_rub)} руб</li>
            ))}
          </ul>
        </details>
      )}
    </div>
  );
}
