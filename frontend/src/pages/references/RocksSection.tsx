import { useEffect, useState } from "react";
import { api } from "../../api/endpoints";
import { useWorkspace } from "../../app/useWorkspace";
import { EditableTable } from "../../components/EditableTable";
import type { DefaultReferences, Rock } from "../../types";

export function RocksSection() {
  const { state, updateReferences, canEdit } = useWorkspace();
  const [defaults, setDefaults] = useState<DefaultReferences | null>(null);
  useEffect(() => { api.workspaceDefaults().then(setDefaults).catch(() => undefined); }, []);
  const rows = state?.references.rock_records ?? [];

  return (
    <section>
      <h4>Горные породы</h4>
      <p className="page-caption">Плотность, прочность и трещиноватость используются в технологическом расчёте БВР на вкладке «Расчёт».</p>
      {canEdit && defaults && (
        <button onClick={() => updateReferences({ rock_records: defaults.rocks })}>Сбросить породы</button>
      )}
      <EditableTable<Rock>
        columns={[
          { key: "name", label: "Порода", type: "text" },
          { key: "density_t_m3", label: "Плотность, т/м³", type: "number", step: 0.01, min: 0.1 },
          { key: "ucs_mpa", label: "Прочность UCS, МПа", type: "number", step: 1, min: 0 },
          { key: "fissuring_ff", label: "Трещиноватость, 1/м", type: "number", step: 0.1, min: 0 },
        ]}
        rows={rows}
        onChange={(next) => updateReferences({ rock_records: next })}
        newRow={canEdit ? () => ({ name: "", density_t_m3: 2.5, ucs_mpa: 100, fissuring_ff: 1 }) : undefined}
        readOnly={!canEdit}
        rowKey={(r, i) => r.id || `rock-${i}`}
      />
      {!canEdit && <p className="page-caption">Справочник пород доступен только для просмотра. Войдите как администратор.</p>}
    </section>
  );
}
