/**
 * Выдвижная панель с разложением стоимости метра бурения (`DrillingBreakdown`)
 * поверх сметы — не модальная: смету за панелью видно и можно листать дальше.
 */
import { DrillingBreakdown } from "../DrillingBreakdown";
import type { BlockEconomics } from "../../../types/blockEconomics";

export function DrillingDrawer({ economics, onClose }: { economics: BlockEconomics; onClose: () => void }) {
  return (
    <aside className="drilling-drawer" role="dialog" aria-modal="false" aria-label="Расчёт бурения">
      <button type="button" className="drilling-drawer-close" aria-label="Закрыть" onClick={onClose}>
        ×
      </button>
      <DrillingBreakdown economics={economics} />
    </aside>
  );
}
