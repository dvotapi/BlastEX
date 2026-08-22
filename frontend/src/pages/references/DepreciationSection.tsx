import { useEffect, useState } from "react";
import { api } from "../../api/endpoints";
import { useWorkspace } from "../../app/useWorkspace";
import { EditableTable } from "../../components/EditableTable";
import type { DefaultReferences, FixedAssetDepreciation } from "../../types";

function withComputedRate(asset: FixedAssetDepreciation): FixedAssetDepreciation {
  const rate = asset.useful_life_months > 0 && asset.productive_shifts_per_month > 0
    ? asset.initial_cost_rub / asset.useful_life_months / asset.productive_shifts_per_month
    : 0;
  return { ...asset, depreciation_per_shift_rub: rate };
}

export function DepreciationSection() {
  const { state, updateReferences, canEdit } = useWorkspace();
  const [defaults, setDefaults] = useState<DefaultReferences | null>(null);
  useEffect(() => { api.workspaceDefaults().then(setDefaults).catch(() => undefined); }, []);
  const rows = state?.references.depreciation_asset_records ?? [];

  function handleChange(next: FixedAssetDepreciation[]) {
    updateReferences({ depreciation_asset_records: next.map(withComputedRate) });
  }

  return (
    <section>
      <h4>Нормы амортизации основных средств</h4>
      <p className="page-caption">Норма в смену рассчитывается автоматически: первоначальная стоимость ÷ СПИ, мес. ÷ смен в месяц.</p>
      {canEdit && defaults && (
        <button onClick={() => updateReferences({ depreciation_asset_records: defaults.depreciation_assets })}>Сбросить ОС</button>
      )}
      <EditableTable<FixedAssetDepreciation>
        columns={[
          { key: "name", label: "Наименование ОС", type: "text" },
          { key: "initial_cost_rub", label: "Первоначальная стоимость, руб", type: "number", step: 1000, min: 0 },
          { key: "useful_life_months", label: "СПИ, мес.", type: "number", step: 1, min: 1 },
          { key: "productive_shifts_per_month", label: "Смен в месяц", type: "number", step: 1, min: 0.1 },
          { key: "depreciation_per_shift_rub", label: "Норма, руб/смена", type: "number", disabled: true },
        ]}
        rows={rows}
        onChange={handleChange}
        newRow={canEdit ? () => withComputedRate({ name: "", initial_cost_rub: 0, useful_life_months: 84, productive_shifts_per_month: 22, depreciation_per_shift_rub: 0 }) : undefined}
        readOnly={!canEdit}
        rowKey={(r, i) => r.name || i}
      />
      {!canEdit && <p className="page-caption">Справочник амортизации ОС доступен только для просмотра. Войдите как администратор.</p>}
    </section>
  );
}
