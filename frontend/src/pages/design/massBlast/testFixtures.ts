// Проект МВ v2 и слои для тестов окна (TASK-018, PR 6). Люди и номера — стендовые.
import { vi } from "vitest";
import type { MassBlastLayer, MassBlastProjectV2, MassBlastValidationV2 } from "../../../types/massBlast";

export function projectV2(changes: Partial<MassBlastProjectV2> = {}): MassBlastProjectV2 {
  return {
    id: "p1",
    name: "Массовый взрыв — блок 66",
    site_code: "ZHK",
    object_name: "Жуков Камень",
    customer_code: "",
    blast_date: "2026-11-20",
    blast_time: "13:00",
    document_profile_code: "STANDARD",
    reference_revision_id: "ref-1",
    blocks: [{ design_id: "d66", code: "66", horizon: "+410", details: { rock_text: "", hydro_text: "", purpose: "", area_m2: null, hole_notes: {} } }],
    responsibilities: [
      { role_code: "blast_manager", employee_code: "Р", employee_name: "Руководитель (тест)", position_name: "руководитель", account_email: "lead@example.test" },
      { role_code: "explosives_supervisor", employee_code: "К", employee_name: "Кладовщик (тест)", position_name: "зав. складом", account_email: "store@example.test" },
    ],
    safety_plan: {},
    charging_schedule: [],
    signal_plan: { profile_code: "STANDARD" },
    guard_posts: [{ code: "1", location: "дорога", responsible_employee_code: "", notes: "" }],
    notifications: [],
    lifecycle_status: "draft",
    version: 3,
    current_revision_id: null,
    created_at: "",
    created_by: "",
    updated_at: "",
    updated_by: "",
    context_version: 2,
    requisites: { project_no: "", tp_basis: "" },
    explosives: { q_tp_kg_m3: null },
    schedule: { station: "станция" },
    personnel: [],
    protected_objects: [],
    safety_overrides: {},
    layout_points: [],
    ...changes,
  } as MassBlastProjectV2;
}

export function validation(changes: Partial<MassBlastValidationV2> = {}): MassBlastValidationV2 {
  return {
    valid: true,
    issues: [],
    context: {
      document_context_version: 2,
      requisites: { tp_basis: "ТП из справочника", customer_approver: { position: "Тех. директор", name: "Заказчиков З. З.", authority: "", is_head: true } },
      zones: { people: { value: 750, factor: "разлёт" }, mechanisms: { value: 500 }, buildings: { value: 100 } },
      blocks_v2: [{ design_id: "d66", code: "66", horizon: "+410", safety: { params: { k_ground: 5, frost: true, hardness_f: 14, sources: { k_ground: "REFERENCE", frost: "REFERENCE", hardness_f: "REFERENCE" } } }, consumption: [], parameter_table: { rows: [] } }],
      graphics: {
        outlines: [[[0, 0], [10, 0], [10, 10], [0, 10]]],
        zones: [{ kind: "people", value_m: 750, rings: [[[-50, -50], [60, -50], [60, 60], [-50, 60]]] }],
        situation: [],
        has_situation: false,
        objects: [],
        points: [],
      },
    },
    defaults: {
      "requisites.tp_basis": { value: "ТП из справочника", source: "REFERENCE" },
      "requisites.project_no": { value: "66-26/МВ", source: "RULE" },
      "explosives.initiation": { value: "Неэлектрическая система инициирования (НСИ)", source: "DESIGN" },
    },
    rememberable: { "requisites.tp_basis": "ТП из справочника", "schedule.station": null },
    ...changes,
  };
}

export function layer(changes: Partial<MassBlastLayer> = {}): MassBlastLayer {
  return {
    id: "l1",
    project_id: "p1",
    kind: "NARYAD",
    project_revision_id: "r1",
    status: "draft",
    version: 2,
    current_revision_id: null,
    stale: false,
    seed: {},
    payload: { reserve: {}, issued: {}, consumed: {}, returned: {} },
    view: {
      lines: [
        { key: "explosive:ВВ:", kind: "explosive", name: "ВВ", unit: "кг", delay_ms: null, project_qty: 1000, reserve_qty: 0, reserve_source: "REFERENCE", issue_qty: 1000, issue_kg: 1000 },
        { key: "primer:ПД:", kind: "primer", name: "ПД", unit: "шт", delay_ms: null, project_qty: 20, reserve_qty: 2, reserve_source: "REFERENCE", issue_qty: 22, issue_kg: 22 },
      ],
    },
    issues: [],
    created_at: "",
    updated_at: "",
    ...changes,
  };
}

/** jsdom не реализует модальный `dialog`. */
export function installDialog(): void {
  HTMLDialogElement.prototype.showModal = vi.fn(function (this: HTMLDialogElement) {
    this.open = true;
  });
  HTMLDialogElement.prototype.close = vi.fn(function (this: HTMLDialogElement) {
    this.open = false;
  });
}
