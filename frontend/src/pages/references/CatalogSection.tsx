import { useEffect, useState } from "react";
import { api } from "../../api/endpoints";
import { useWorkspace } from "../../app/useWorkspace";
import { EditableTable, type EditableColumn } from "../../components/EditableTable";
import type { CatalogCategory, CatalogItem, DefaultReferences } from "../../types";

function CategoryTable({
  category, unit, title, showMass, showLength,
}: { category: CatalogCategory; unit: string; title: string; showMass?: boolean; showLength?: boolean }) {
  const { state, updateSnapshot, canEdit } = useWorkspace();
  const catalog = state?.snapshot.cost_catalog_records ?? [];
  const rows = catalog.filter((i) => i.category === category);

  const columns: EditableColumn<CatalogItem>[] = [
    { key: "id", label: "Код", type: "text" },
    { key: "name", label: "Наименование", type: "text" },
    { key: "price", label: "Цена, руб", type: "number", step: 0.01, min: 0 },
  ];
  if (showMass) columns.push({ key: "mass_kg", label: "Масса патрона, кг", type: "number", step: 0.001, min: 0 });
  if (showLength) columns.push({ key: "length_m", label: "Длина, м", type: "number", step: 0.1, min: 0 });
  columns.push({ key: "note", label: "Примечание", type: "text" });

  function handleChange(next: CatalogItem[]) {
    const withMeta = next.map((row) => ({ ...row, category, unit }));
    const rest = catalog.filter((i) => i.category !== category);
    updateSnapshot({ cost_catalog_records: [...rest, ...withMeta] });
  }

  return (
    <details className="catalog-category" open>
      <summary>{title}</summary>
      <EditableTable<CatalogItem>
        columns={columns}
        rows={rows}
        onChange={handleChange}
        newRow={canEdit ? () => ({ id: "", name: "", category, unit, price: 0, note: "" }) : undefined}
        readOnly={!canEdit}
        rowKey={(r, i) => r.id || i}
      />
    </details>
  );
}

export function CatalogSection() {
  const { updateSnapshot, canEdit } = useWorkspace();
  const [defaults, setDefaults] = useState<DefaultReferences | null>(null);
  useEffect(() => { api.workspaceDefaults().then(setDefaults).catch(() => undefined); }, []);

  return (
    <section>
      <h4>Номенклатура и цены (ВВ, СВ, СИ)</h4>
      <p className="page-caption">Цены без НДС. Номенклатура подбирается автоматически по техническому расчёту.</p>
      {canEdit && defaults && (
        <button onClick={() => updateSnapshot({ cost_catalog_records: defaults.catalog })}>Сбросить номенклатуру</button>
      )}
      {!canEdit && <p className="page-caption">Номенклатура доступна только для просмотра. Войдите как администратор.</p>}
      <CategoryTable category="explosive" unit="кг" title="ВВ — взрывчатые вещества" />
      <CategoryTable category="detonator" unit="кг" title="СВ — промежуточные детонаторы" showMass />
      <CategoryTable category="downhole_nsi" unit="шт" title="СИ — НСИ скважинное (Искра-С, Rionel)" showLength />
      <CategoryTable category="surface_nsi" unit="шт" title="СИ — НСИ поверхностное (Искра-П)" />
      <CategoryTable category="start_nsi" unit="шт" title="СИ — НСИ стартовое (Искра-Старт)" />
    </section>
  );
}
