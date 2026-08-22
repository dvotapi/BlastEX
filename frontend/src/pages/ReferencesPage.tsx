import { useState } from "react";
import { CatalogSection } from "./references/CatalogSection";
import { DepreciationSection } from "./references/DepreciationSection";
import { ExplosivesSection } from "./references/ExplosivesSection";
import { FixedCostsSection } from "./references/FixedCostsSection";
import { OperationsSection } from "./references/OperationsSection";
import { RocksSection } from "./references/RocksSection";

const TABS = [
  "Горные породы",
  "Взрывчатые вещества",
  "Амортизация ОС",
  "Объекты и станки",
  "Номенклатура и цены",
  "Постоянные расходы",
] as const;

export function ReferencesPage() {
  const [tab, setTab] = useState<(typeof TABS)[number]>(TABS[0]);

  return (
    <div className="page-content">
      <h2>Справочники</h2>
      <p className="page-caption">
        Технические и сметные справочники. Редактирование доступно администратору и редактору справочников.
        Изменения сохраняются кнопкой «Сохранить» в панели над вкладками.
      </p>
      <nav className="sub-tabs">
        {TABS.map((t) => <button key={t} className={t === tab ? "active" : ""} onClick={() => setTab(t)}>{t}</button>)}
      </nav>
      {tab === "Горные породы" && <RocksSection />}
      {tab === "Взрывчатые вещества" && <ExplosivesSection />}
      {tab === "Амортизация ОС" && <DepreciationSection />}
      {tab === "Объекты и станки" && <OperationsSection />}
      {tab === "Номенклатура и цены" && <CatalogSection />}
      {tab === "Постоянные расходы" && <FixedCostsSection />}
    </div>
  );
}
