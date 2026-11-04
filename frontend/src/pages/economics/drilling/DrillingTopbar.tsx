/**
 * Контекст страницы «Бурение» в шапке приложения: технический паспорт
 * (выбор, как на «Экономике блока»), объект работ, объём бурения, станок и
 * цена метра в смете. Это контекст всей страницы, а не её содержимое, поэтому
 * стоит там же, где на «Экономике» стоят селекторы объекта и паспорта
 * (`TopbarSelectors`), и не отнимает высоту у панелей страницы.
 *
 * Переносится в шапку через слот (`topbarSlot.tsx`); без слота — тесты
 * компонентов без `AppShell` — рисуется на месте.
 */
import { createPortal } from "react-dom";
import { useTopbarTitleSlot } from "../../../app/topbarSlot";
import type { TechnicalPassport } from "../../../types/blockEconomics";

export type DrillingTopbarProps = {
  passports: TechnicalPassport[];
  selectedId: string;
  onSelect: (id: string) => void;
  siteLabel: string;
  siteTitle?: string;
  volumeLabel: string;
  rigLabel: string;
  priceLabel: string;
  /** Ответ по изменённому черновику ещё не пришёл: цена от прежних параметров. */
  priceStale?: boolean;
};

export function DrillingTopbar({
  passports,
  selectedId,
  onSelect,
  siteLabel,
  siteTitle,
  volumeLabel,
  rigLabel,
  priceLabel,
  priceStale,
}: DrillingTopbarProps) {
  const slot = useTopbarTitleSlot();

  const content = (
    <div className="topbar-selectors drilling-topbar">
      <label className="topbar-selector is-select">
        <span>Технический паспорт</span>
        <select aria-label="Технический паспорт" value={selectedId} onChange={(event) => onSelect(event.target.value)}>
          {passports.map((item) => (
            <option key={item.id} value={item.id}>
              {item.object_name} · вер. {item.version_no}
            </option>
          ))}
        </select>
      </label>
      <div className="topbar-selector" title={siteTitle}>
        <span>Объект работ</span>
        <b>{siteLabel || "—"}</b>
      </div>
      <div className="topbar-selector">
        <span>Объём бурения</span>
        <b>{volumeLabel}</b>
      </div>
      <div className="topbar-selector">
        <span>Станок</span>
        <b>{rigLabel}</b>
      </div>
      <div
        className="topbar-selector"
        title="Только строки станка по активному черновику сметы: оснастка, ДТ, запчасти, амортизация, страховка, ТОиР, выпуск и медосмотр. Полная себестоимость метра — «С ФОТ» и «Без ФОТ» на панели «Что двигает цену метра»."
      >
        <span>Станок, 1 п.м. в смете</span>
        <b className={priceStale ? "is-stale" : undefined}>
          {priceLabel}
          {priceStale && <small className="rig-shifts-stale"> считается…</small>}
        </b>
      </div>
    </div>
  );

  return slot ? createPortal(content, slot) : content;
}
