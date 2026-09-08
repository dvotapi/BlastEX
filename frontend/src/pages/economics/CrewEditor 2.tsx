import { NumericInput } from "./NumericInput";
import type { CodeName, CrewMemberInput } from "../../types/blockEconomics";

/**
 * Состав бригады: численность и смены на блок.
 *
 * Пустые смены означают «взять норматив должности либо вывести из
 * производительности техники», поэтому поле не заполняется нулём.
 */
export function CrewEditor({
  crew,
  positions,
  onChange,
}: {
  crew: CrewMemberInput[];
  positions: CodeName[];
  onChange: (crew: CrewMemberInput[]) => void;
}) {
  function update(index: number, patch: Partial<CrewMemberInput>) {
    onChange(crew.map((member, i) => (i === index ? { ...member, ...patch } : member)));
  }

  function add() {
    const used = new Set(crew.map((member) => member.position_code));
    const next = positions.find((item) => !used.has(item.code)) ?? positions[0];
    if (!next) return;
    onChange([...crew, { position_code: next.code, headcount: 1, shifts_per_block: null }]);
  }

  return (
    <div className="crew-editor">
      <div className="crew-editor-head">
        <span>Должность</span>
        <span>Чел.</span>
        <span>Смен на блок</span>
        <span />
      </div>
      {crew.length === 0 && <p className="page-caption">Шаблон бригады для пакета не заполнен.</p>}
      {crew.map((member, index) => (
        <div className="crew-editor-row" key={`${member.position_code}-${index}`}>
          <select
            value={member.position_code}
            onChange={(event) => update(index, { position_code: event.target.value })}
            aria-label="Должность"
          >
            {positions.map((item) => (
              <option key={item.code} value={item.code}>{item.name}</option>
            ))}
          </select>
          <NumericInput
            value={member.headcount}
            min={0}
            step={1}
            ariaLabel="Численность, чел."
            onChange={(value) => update(index, { headcount: value ?? "0" })}
          />
          <NumericInput
            value={member.shifts_per_block}
            allowEmpty
            min={0}
            step={0.1}
            placeholder="норматив"
            ariaLabel="Смен на блок"
            onChange={(value) => update(index, { shifts_per_block: value })}
          />
          <button
            type="button"
            className="row-remove"
            onClick={() => onChange(crew.filter((_, i) => i !== index))}
            aria-label="Убрать должность"
          >
            ×
          </button>
        </div>
      ))}
      <button type="button" className="row-add" onClick={add} disabled={!positions.length}>
        + Должность
      </button>
    </div>
  );
}
