import type { TeamReferences, WorkspaceSnapshot } from "../types";

type ReferenceRow = { id?: string };
type SnapshotRow = { row_id?: string };

function createRowId(prefix: string, index: number): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return `${prefix}-${crypto.randomUUID()}`;
  }
  return `${prefix}-${Date.now()}-${index}-${Math.random().toString(36).slice(2)}`;
}

function withStableIds<T extends ReferenceRow>(rows: T[], prefix: string): T[] {
  const used = new Set<string>();
  return rows.map((row, index) => {
    const currentId = typeof row.id === "string" ? row.id.trim() : "";
    const id = currentId && !used.has(currentId) ? currentId : createRowId(prefix, index);
    used.add(id);
    return id === row.id ? row : { ...row, id };
  });
}

function withStableRowIds<T extends SnapshotRow>(rows: T[], prefix: string): T[] {
  const used = new Set<string>();
  return rows.map((row, index) => {
    const currentId = typeof row.row_id === "string" ? row.row_id.trim() : "";
    const rowId = currentId && !used.has(currentId) ? currentId : createRowId(prefix, index);
    used.add(rowId);
    return rowId === row.row_id ? row : { ...row, row_id: rowId };
  });
}

/**
 * Рабочие справочники исторически не содержали идентификаторов строк.
 * Добавляем их на границе UI и сохраняем в payload как безвредное мета-поле.
 * Это не меняет доменные поля, но не даёт React пересоздавать строку при
 * редактировании её наименования.
 */
export function normalizeReferenceRows(references: TeamReferences): TeamReferences {
  return {
    ...references,
    work_object_records: withStableIds(references.work_object_records, "work-object"),
    drill_rig_records: withStableIds(references.drill_rig_records, "drill-rig"),
    rock_records: withStableIds(references.rock_records, "rock"),
    explosive_records: withStableIds(references.explosive_records, "explosive"),
    depreciation_asset_records: withStableIds(references.depreciation_asset_records, "asset"),
  };
}

export function normalizeReferencePatch(patch: Partial<TeamReferences>): Partial<TeamReferences> {
  return {
    ...patch,
    ...(patch.work_object_records
      ? { work_object_records: withStableIds(patch.work_object_records, "work-object") }
      : {}),
    ...(patch.drill_rig_records
      ? { drill_rig_records: withStableIds(patch.drill_rig_records, "drill-rig") }
      : {}),
    ...(patch.rock_records
      ? { rock_records: withStableIds(patch.rock_records, "rock") }
      : {}),
    ...(patch.explosive_records
      ? { explosive_records: withStableIds(patch.explosive_records, "explosive") }
      : {}),
    ...(patch.depreciation_asset_records
      ? { depreciation_asset_records: withStableIds(patch.depreciation_asset_records, "asset") }
      : {}),
  };
}

export function normalizeSnapshotRows(snapshot: WorkspaceSnapshot): WorkspaceSnapshot {
  return {
    ...snapshot,
    cost_catalog_records: withStableRowIds(snapshot.cost_catalog_records, "catalog"),
    fixed_cost_records: withStableRowIds(snapshot.fixed_cost_records, "fixed-cost"),
    labor_catalog_records: withStableRowIds(snapshot.labor_catalog_records, "labor-position"),
    labor_assignment_records: withStableRowIds(snapshot.labor_assignment_records, "labor-assignment"),
  };
}

export function normalizeSnapshotPatch(patch: Partial<WorkspaceSnapshot>): Partial<WorkspaceSnapshot> {
  return {
    ...patch,
    ...(patch.cost_catalog_records
      ? { cost_catalog_records: withStableRowIds(patch.cost_catalog_records, "catalog") }
      : {}),
    ...(patch.fixed_cost_records
      ? { fixed_cost_records: withStableRowIds(patch.fixed_cost_records, "fixed-cost") }
      : {}),
    ...(patch.labor_catalog_records
      ? { labor_catalog_records: withStableRowIds(patch.labor_catalog_records, "labor-position") }
      : {}),
    ...(patch.labor_assignment_records
      ? { labor_assignment_records: withStableRowIds(patch.labor_assignment_records, "labor-assignment") }
      : {}),
  };
}
