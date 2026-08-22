import { useEffect, useState } from "react";
import { api } from "../../api/endpoints";
import { useWorkspace } from "../../app/useWorkspace";
import { EditableTable } from "../../components/EditableTable";
import type { DefaultReferences, DrillRig, WorkObject } from "../../types";

export function OperationsSection() {
  const { state, updateReferences, canEdit } = useWorkspace();
  const [defaults, setDefaults] = useState<DefaultReferences | null>(null);
  useEffect(() => { api.workspaceDefaults().then(setDefaults).catch(() => undefined); }, []);
  const objects = state?.references.work_object_records ?? [];
  const rigs = state?.references.drill_rig_records ?? [];
  const drillingPrice = state?.drilling_price_per_m ?? 0;

  return (
    <section>
      <h4>Объекты работ (карьеры / месторождения)</h4>
      <p className="page-caption">Мобилизация и цена ДТ подставляются в расчёт бурения для выбранного объекта.</p>
      {canEdit && defaults && (
        <button onClick={() => updateReferences({ work_object_records: defaults.work_objects })}>Сбросить объекты</button>
      )}
      <EditableTable<WorkObject>
        columns={[
          { key: "name", label: "Объект работ", type: "text" },
          { key: "mobilization_km", label: "Мобилизация, км", type: "number", step: 1, min: 0 },
          { key: "diesel_price_ton_rub", label: "Цена ДТ, руб/т", type: "number", step: 1000, min: 0 },
        ]}
        rows={objects}
        onChange={(next) => updateReferences({ work_object_records: next })}
        newRow={canEdit ? () => ({ name: "", mobilization_km: 0, diesel_price_ton_rub: null }) : undefined}
        readOnly={!canEdit}
        rowKey={(r, i) => r.name || i}
      />
      {!canEdit && <p className="page-caption">Объекты работ доступны только для просмотра. Войдите как администратор.</p>}

      <h4>Буровые станки</h4>
      <p className="page-caption">Амортизация и расход топлива используются в калькуляторе бурения.</p>
      {canEdit && defaults && (
        <button onClick={() => updateReferences({ drill_rig_records: defaults.drill_rigs })}>Сбросить станки</button>
      )}
      <EditableTable<DrillRig>
        columns={[
          { key: "name", label: "Станок", type: "text" },
          { key: "depreciation_per_shift_rub", label: "Амортизация, руб/смена", type: "number", step: 100, min: 0 },
          { key: "fuel_l_per_h", label: "Расход, л/ч", type: "number", step: 0.1, min: 0 },
        ]}
        rows={rigs}
        onChange={(next) => updateReferences({ drill_rig_records: next })}
        newRow={canEdit ? () => ({ name: "", depreciation_per_shift_rub: 0, fuel_l_per_h: 0 }) : undefined}
        readOnly={!canEdit}
        rowKey={(r, i) => r.name || i}
      />
      {!canEdit && <p className="page-caption">Справочник станков доступен только для просмотра. Войдите как администратор.</p>}

      <h4>Стоимость бурения</h4>
      <p className="metric-standalone"><strong>{drillingPrice.toLocaleString("ru-RU", { maximumFractionDigits: 2 })}</strong> руб/п.м.</p>
      <p className="page-caption">Рассчитывается на вкладке «Бурение».</p>
    </section>
  );
}
