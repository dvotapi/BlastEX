import type { ReactNode } from "react";
import { plural } from "../../lib/plural";
import { formatFieldValue, fieldIndex, parseNumber } from "./schemaFields";
import type { ReferenceSectionSchema } from "../../types/referenceSchema";
import type { DraftItem } from "./RecordForm";

export type MatrixMode = "rocks" | "sites" | "list";

type Column = { code: string; label: string };

/**
 * Матрица «станок × порода» — единственное разделоспецифичное представление.
 *
 * Норма подбирается по убыванию точности: станок + карьер, станок + порода,
 * станок по умолчанию. Поэтому пустая ячейка — не пробел, а «берётся норма по
 * умолчанию», а станок без нормы по умолчанию — ошибка.
 */
export function DrillingConditionsMatrix({
  section,
  rows,
  rigs,
  rocks,
  sites,
  mode,
  onMode,
  selected,
  changed,
  canEdit,
  onSelect,
  onCreate,
  listView,
}: {
  section: ReferenceSectionSchema;
  rows: DraftItem[];
  rigs: DraftItem[];
  rocks: DraftItem[];
  sites: DraftItem[];
  mode: MatrixMode;
  onMode: (mode: MatrixMode) => void;
  selected: string;
  changed: Set<string>;
  canEdit: boolean;
  onSelect: (rowId: string) => void;
  onCreate: (prefill: Record<string, unknown>) => void;
  listView: ReactNode;
}) {
  const fields = fieldIndex(section.json_schema);
  const byRig = (rig: string) => rows.filter((row) => row.payload.equipment_type_code === rig);
  const missingDefault = rigs.filter(
    (rig) => !byRig(rig.code).some((row) => !row.payload.rock_code && !row.payload.site_code),
  );

  const columns: Column[] =
    mode === "sites"
      ? [{ code: "", label: "По умолчанию" }, ...sites.map((site) => ({ code: site.code, label: site.name || site.code }))]
      : [{ code: "", label: "По умолчанию" }, ...rocks.map((rock) => ({ code: rock.code, label: rock.name || rock.code }))];

  /**
   * Все нормы ячейки, а не первая подходящая: у одного сочетания «станок ×
   * порода» может быть уточнение по карьеру, и раньше вторая запись просто
   * пропадала с экрана — открыть её можно было только видом «Списком».
   */
  function matches(rig: string, column: string): DraftItem[] {
    const candidates = byRig(rig);
    if (mode === "sites") {
      return candidates.filter((row) => String(row.payload.site_code ?? "") === column);
    }
    return candidates.filter((row) => String(row.payload.rock_code ?? "") === column);
  }

  /** Уточнение записи в ячейке: чем она отличается от соседних по той же клетке. */
  function cellLabel(row: DraftItem): string {
    const named = (records: DraftItem[], code: unknown) =>
      typeof code === "string" && code ? records.find((item) => item.code === code)?.name || code : "";
    if (mode === "sites") return named(rocks, row.payload.rock_code) || "по умолчанию";
    // Наименование карьера уже содержит слово «карьер», добавлять его не нужно.
    return named(sites, row.payload.site_code);
  }

  function prefill(rig: string, column: string): Record<string, unknown> {
    if (mode === "sites") return { equipment_type_code: rig, site_code: column || null };
    return { equipment_type_code: rig, rock_code: column || null };
  }

  function summary(row: DraftItem): string {
    const parts = [
      formatFieldValue(row.payload.fuel_l_per_m, fields.get("fuel_l_per_m")),
      formatFieldValue(row.payload.bit_life_m, fields.get("bit_life_m")),
    ].filter((part) => part !== "—");
    const label = cellLabel(row);
    if (label) parts.unshift(label);
    return parts.join(" · ");
  }

  return (
    <section className="ref-list-panel">
      <header className="ref-list-head">
        <div>
          <h3>{section.label}</h3>
          <p className="ref-list-note">
            Скорость, топливо и ресурс коронки зависят от того, какой станок бурит какую породу. Пустая ячейка — берётся
            норма станка по умолчанию.
          </p>
        </div>
        {missingDefault.length > 0 && (
          <span className="ref-warning-badge">
            {missingDefault.length} {plural(missingDefault.length, ["станок", "станка", "станков"])} без нормы по
            умолчанию
          </span>
        )}
      </header>

      <div className="ref-list-filters">
        <div className="ref-segments">
          <button type="button" className={mode === "rocks" ? "active" : ""} onClick={() => onMode("rocks")}>
            По породам
          </button>
          <button type="button" className={mode === "sites" ? "active" : ""} onClick={() => onMode("sites")}>
            По карьерам
          </button>
          <button type="button" className={mode === "list" ? "active" : ""} onClick={() => onMode("list")}>
            Списком
          </button>
        </div>
      </div>

      {mode === "list" ? (
        listView
      ) : (
        <div className="ref-table-scroll">
          <table className="ref-table ref-matrix">
            <thead>
              <tr>
                <th>Станок</th>
                {columns.map((column) => (
                  <th key={column.code || "default"}>{column.label}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rigs.map((rig) => (
                <tr key={rig.row_id}>
                  <td className="ref-matrix-rig">
                    <b>{rig.name || rig.code}</b>
                    <small>{rig.code}</small>
                  </td>
                  {columns.map((column) => {
                    const cellRows = matches(rig.code, column.code);
                    const isDefaultColumn = column.code === "";
                    if (!cellRows.length) {
                      const missing = isDefaultColumn;
                      return (
                        <td
                          key={column.code || "default"}
                          className={`ref-matrix-cell empty${missing ? " missing" : ""}`}
                          onClick={() => canEdit && onCreate(prefill(rig.code, column.code))}
                        >
                          {missing ? "нет нормы по умолчанию" : canEdit ? "по умолчанию · добавить" : "по умолчанию"}
                        </td>
                      );
                    }
                    return (
                      <td key={column.code || "default"} className="ref-matrix-cell">
                        {cellRows.map((row) => (
                          <button
                            key={row.row_id}
                            type="button"
                            className={`ref-matrix-entry${row.row_id === selected ? " selected" : ""}${
                              changed.has(row.row_id) ? " changed" : ""
                            }`}
                            onClick={() => onSelect(row.row_id)}
                          >
                            <b>{formatFieldValue(parseNumber(row.payload.tech_speed_m_per_h), fields.get("tech_speed_m_per_h"))}</b>
                            <small>{summary(row)}</small>
                          </button>
                        ))}
                        {canEdit && (
                          <button
                            type="button"
                            className="ref-matrix-add"
                            title="Добавить ещё одну норму для этого сочетания"
                            onClick={() => onCreate(prefill(rig.code, column.code))}
                          >
                            + уточнение
                          </button>
                        )}
                      </td>
                    );
                  })}
                </tr>
              ))}
              {rigs.length === 0 && (
                <tr className="ref-table-empty">
                  <td colSpan={columns.length + 1}>
                    Нет типов техники с видом «Буровой станок» — заведите их в разделе «Типы оборудования».
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
