/**
 * Раздел «Бурение»: способ исполнения (собственными силами или субподряд) —
 * общий переключатель, дальше каждый способ ведёт свой редактор. Переносить
 * данные между способами не нужно: параметры обоих живут в одних и тех же
 * полях `ModelParameters`, но модель считает только выбранный способ.
 */
import { OwnDrillingEditor } from "../drilling/OwnDrillingEditor";
import { SubcontractDrillingEditor } from "../drilling/SubcontractDrillingEditor";
import type { ModelParameters } from "../../../types/blockEconomics";
import type { SectionEditorProps } from "./types";

export type DrillingSectionProps = SectionEditorProps & {
  /** Открыть отдельный калькулятор бурения (Cost V1, вкладка «Бурение»); подключает задача 9. */
  onOpenDrillingPage: () => void;
  /**
   * Каталог (`defaults`) устарел и его нужно перечитать — зовёт
   * `SubcontractDrillingEditor` сразу после публикации тарифа субподряда в
   * справочник: без этого выбранный код не находится в старом снимке
   * `defaults.subcontract_rates`, и выбор тарифа выглядит сброшенным.
   */
  onDefaultsChanged: () => void;
};

export function DrillingSection(props: DrillingSectionProps) {
  const { group, params, defaults, economics, volume, canEdit, onChange, onOpenDrillingPage, onDefaultsChanged } =
    props;

  function setExecutor(executor: ModelParameters["drilling_executor"]) {
    onChange({ drilling_executor: executor });
  }

  return (
    <div className="drilling-section">
      <fieldset className="drilling-executor" disabled={!canEdit}>
        <legend>Исполнение</legend>
        <label>
          <input
            type="radio"
            name="drilling_executor"
            value="OWN"
            checked={params.drilling_executor === "OWN"}
            onChange={() => setExecutor("OWN")}
          />
          Собственными силами
        </label>
        <label>
          <input
            type="radio"
            name="drilling_executor"
            value="SUBCONTRACTOR"
            checked={params.drilling_executor === "SUBCONTRACTOR"}
            onChange={() => setExecutor("SUBCONTRACTOR")}
          />
          Субподряд
        </label>
      </fieldset>
      {params.drilling_executor === "OWN" ? (
        <OwnDrillingEditor
          group={group}
          params={params}
          defaults={defaults}
          economics={economics}
          volume={volume}
          canEdit={canEdit}
          onChange={onChange}
          onOpenDrillingPage={onOpenDrillingPage}
        />
      ) : (
        <SubcontractDrillingEditor
          group={group}
          params={params}
          defaults={defaults}
          economics={economics}
          volume={volume}
          canEdit={canEdit}
          onChange={onChange}
          onDefaultsChanged={onDefaultsChanged}
        />
      )}
    </div>
  );
}
