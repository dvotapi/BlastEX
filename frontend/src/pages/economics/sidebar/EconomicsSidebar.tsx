/**
 * Липкий сайдбар вкладки «Экономика блока»: кольцо структуры себестоимости,
 * лестница формирования цены, ключевые итоги.
 *
 * Собирает три независимых блока (`CostStructureDonut`, `PriceFormation`,
 * `EconomicsTotals`) в одну колонку — сам ничего не считает, только
 * прокидывает уже посчитанные `economics` и состояние диаграммы (единица
 * легенды, выделенный раздел), которым владеет страница.
 */
import { CostStructureDonut } from "./CostStructureDonut";
import { EconomicsTotals } from "./EconomicsTotals";
import { PriceFormation } from "./PriceFormation";
import type { EstimateGroup, EstimateGroupCode } from "../estimateModel";
import type { BlockEconomics } from "../../../types/blockEconomics";

export function EconomicsSidebar(props: {
  economics: BlockEconomics;
  groups: EstimateGroup[];
  unit: "₽" | "₽/м³";
  onUnitChange: (unit: "₽" | "₽/м³") => void;
  highlighted: EstimateGroupCode | null;
  onSelect: (code: EstimateGroupCode) => void;
}) {
  const { economics, groups, unit, onUnitChange, highlighted, onSelect } = props;
  const costPerM3 = economics.block_volume_m3 > 0 ? economics.price_per_m3.full : null;

  return (
    <aside className="economics-sidebar">
      <CostStructureDonut
        groups={groups}
        costPerM3={costPerM3}
        unit={unit}
        onUnitChange={onUnitChange}
        highlighted={highlighted}
        onSelect={onSelect}
      />
      <PriceFormation economics={economics} />
      <EconomicsTotals economics={economics} />
    </aside>
  );
}
