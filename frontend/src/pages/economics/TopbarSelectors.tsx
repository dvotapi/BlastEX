/**
 * Объект, технический паспорт и ревизия справочников — в шапке приложения.
 *
 * Это контекст всей страницы, а не её содержимое: от них зависит каждая
 * цифра сметы. В шапке они стоят там же, где на других листах стоят команда
 * и объект работ, и не отнимают высоту у самой сметы.
 *
 * Как и кнопка справки, блок переносится в шапку через слот (`topbarSlot.tsx`).
 * Если слота нет — тесты компонентов без `AppShell` — рисуется на месте.
 */
import { createPortal } from "react-dom";
import { useTopbarTitleSlot } from "../../app/topbarSlot";
import type { TechnicalPassport } from "../../types/blockEconomics";

export function TopbarSelectors({
  passports,
  selectedId,
  onSelect,
  siteLabel,
  siteTitle,
  revisionLabel,
  revisionTitle,
}: {
  passports: TechnicalPassport[];
  selectedId: string;
  onSelect: (id: string) => void;
  siteLabel: string;
  siteTitle?: string;
  revisionLabel: string;
  revisionTitle?: string;
}) {
  const slot = useTopbarTitleSlot();

  const content = (
    <div className="topbar-selectors">
      <div className="topbar-selector" title={siteTitle}>
        <span>Объект работ</span>
        <b>{siteLabel || "—"}</b>
      </div>
      <label className="topbar-selector is-select">
        <span>Технический паспорт</span>
        <select
          aria-label="Технический паспорт"
          value={selectedId}
          onChange={(event) => onSelect(event.target.value)}
        >
          {passports.map((item) => (
            <option key={item.id} value={item.id}>
              {item.object_name} · вер. {item.version_no}
            </option>
          ))}
        </select>
      </label>
      <div className="topbar-selector" title={revisionTitle}>
        <span>Ревизия справочников паспорта</span>
        <b>{revisionLabel || "—"}</b>
      </div>
    </div>
  );

  return slot ? createPortal(content, slot) : content;
}
