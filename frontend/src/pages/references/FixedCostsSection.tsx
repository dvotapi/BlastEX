import { useEffect, useState } from "react";
import { api } from "../../api/endpoints";
import { useWorkspace } from "../../app/useWorkspace";
import { EditableTable } from "../../components/EditableTable";
import { FIXED_COST_SECTIONS } from "../../types";
import type { DefaultReferences, FixedCostItem } from "../../types";

function SectionTable({ section, title }: { section: string; title: string }) {
  const { state, updateSnapshot, canEdit } = useWorkspace();
  const items = state?.snapshot.fixed_cost_records ?? [];
  const rows = items.filter((i) => i.section === section);

  function handleChange(next: FixedCostItem[]) {
    const withSection = next.map((row) => ({ ...row, section }));
    const rest = items.filter((i) => i.section !== section);
    updateSnapshot({ fixed_cost_records: [...rest, ...withSection] });
  }

  return (
    <details className="catalog-category" open={section === "2.1" || section === "2.3"}>
      <summary>{section} — {title}</summary>
      <EditableTable<FixedCostItem>
        columns={[
          { key: "id", label: "Код", type: "text" },
          { key: "name", label: "Наименование", type: "text" },
          { key: "amount_rub", label: "Сумма, руб на блок", type: "number", step: 100, min: 0 },
          { key: "note", label: "Примечание", type: "text" },
          { key: "enabled", label: "Учитывать", type: "checkbox" },
        ]}
        rows={rows}
        onChange={handleChange}
        newRow={canEdit ? () => ({ id: "", section, name: "", amount_rub: 0, note: "", enabled: true }) : undefined}
        readOnly={!canEdit}
        rowKey={(r, i) => r.id || i}
      />
    </details>
  );
}

export function FixedCostsSection() {
  const { updateSnapshot, canEdit } = useWorkspace();
  const [defaults, setDefaults] = useState<DefaultReferences | null>(null);
  useEffect(() => { api.workspaceDefaults().then(setDefaults).catch(() => undefined); }, []);

  return (
    <section>
      <h4>Постоянные расходы (блок 2)</h4>
      <p className="page-caption">Суммы на блок для текущего сценария. Удельная стоимость пересчитывается при изменении объёма блока.</p>
      {canEdit && defaults && (
        <button onClick={() => updateSnapshot({ fixed_cost_records: defaults.fixed_costs })}>Сбросить постоянные расходы</button>
      )}
      {!canEdit && <p className="page-caption">Постоянные расходы доступны только для просмотра. Войдите как администратор.</p>}
      {FIXED_COST_SECTIONS.map(([code, title]) => <SectionTable key={code} section={code} title={title} />)}
    </section>
  );
}
