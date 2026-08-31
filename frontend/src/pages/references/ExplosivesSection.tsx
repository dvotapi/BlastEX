import { useEffect, useState } from "react";
import { api } from "../../api/endpoints";
import { useWorkspace } from "../../app/useWorkspace";
import { EditableTable } from "../../components/EditableTable";
import type { DefaultReferences, Explosive } from "../../types";

export function ExplosivesSection() {
  const { state, updateReferences, canEdit } = useWorkspace();
  const [defaults, setDefaults] = useState<DefaultReferences | null>(null);
  useEffect(() => { api.workspaceDefaults().then(setDefaults).catch(() => undefined); }, []);
  const rows = state?.references.explosive_records ?? [];

  return (
    <section>
      <h4>Взрывчатые вещества</h4>
      <p className="page-caption">Плотность заряжания и теплота взрыва используются в технологическом расчёте БВР на вкладке «Расчёт».</p>
      {canEdit && defaults && (
        <button onClick={() => updateReferences({ explosive_records: defaults.explosives })}>Сбросить ВВ</button>
      )}
      <EditableTable<Explosive>
        columns={[
          { key: "key", label: "Ключ в UI", type: "text" },
          { key: "name", label: "Наименование", type: "text" },
          { key: "density_t_m3", label: "Плотность, т/м³", type: "number", step: 0.01, min: 0.01 },
          { key: "power_mj_kg", label: "Теплота, МДж/кг", type: "number", step: 0.01, min: 0.01 },
          { key: "chart_label", label: "Подпись на схеме", type: "text" },
        ]}
        rows={rows}
        onChange={(next) => updateReferences({ explosive_records: next })}
        newRow={canEdit ? () => ({ key: "", name: "", density_t_m3: 1, power_mj_kg: 3, chart_label: "" }) : undefined}
        readOnly={!canEdit}
        rowKey={(r, i) => r.id || `explosive-${i}`}
      />
      {!canEdit && <p className="page-caption">Справочник ВВ доступен только для просмотра. Войдите как администратор.</p>}
    </section>
  );
}
