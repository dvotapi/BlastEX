import type { DrillPassport, DrillPassportIssue, DrillPassportValidation } from "../../../types/drillPassport";

// Паспорт и проверка блока 66 для тестов окна и панели.
const signer = { position: "", organization: "", name: "" };

export function passport66(): DrillPassport {
  return {
    id: "p1", design_id: "block-66", passport_no: "66-26/Б", passport_date: "2026-11-09", status: "draft", version: 3,
    current_revision_id: null, created_at: "", created_by: "", updated_at: "", updated_by: "",
    payload: {
      agreed_by: { position: "Главный инженер", organization: "АО «КГОК»", name: "Иванов И. И." },
      approved_by: signer, compiled_by: signer, basis: "", site_code: "ZHK", object_name: "Жуков Камень",
      customer: "", block: "66", horizon: "+410", block_area_m2: null, rig_type_code: "JK830", profile_code: "",
      rig_name: "JK830-2", rig_number: "7", bit_diameter_mm: 140, drilling_start: "", drilling_end: "",
      site_preparation: "бульдозером", stakeout: "", drilling_order: "", access_route: "", power_lines: "",
      adjacent_works: "", acceptance: "исполнительная съёмка", extra_approvals: ["маркшейдер", "геолог"],
      tol_depth_m: 0.3, tol_collar_m: 0.3, personnel: [{ name: "Петров", position: "машинист" }],
      alpha_deg: null, gamma_deg: null, axis_offset_m: 1.2,
      bench_height_for_s_m: 10,
    },
  };
}

export const warning = (code: string, path = ""): DrillPassportIssue => ({ level: "warning", code, message: code, path });

export function validation66(issues: DrillPassportIssue[] = []): DrillPassportValidation {
  return {
    valid: !issues.some((issue) => issue.level === "error"),
    issues,
    summary: {},
    first_row_check: {
      h1_m: 11.7, prism_m: 1.98, s_m: 2.0, c_min_m: 0.8, c_m: 1.72, c_max_m: 3.08, w_m: 5.94, w_max_m: 3.811, hs_m: 10,
      hs_source: "MANUAL_OVERRIDE", issues: [],
    },
    inputs: { alpha_deg: 75, gamma_deg: 65, axis_offset_m: 1.2, bench_height_for_s_m: 10, block_area_m2: 2790 },
    provenance: {
      alpha_deg: "REFERENCE", gamma_deg: "REFERENCE", axis_offset_m: "MANUAL_OVERRIDE", bench_height_for_s_m: "MANUAL_OVERRIDE",
      block_area_m2: "DESIGN", c_m: "DESIGN", w_m: "DESIGN", w_max_m: "DESIGN",
    },
  };
}
