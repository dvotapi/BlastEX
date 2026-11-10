import { describe, expect, it } from "vitest";
import type { DrillPassportIssue } from "../../../types/drillPassport";
import {
  ackKey,
  canRelease,
  checkRows,
  FIELD_GROUPS,
  formErrors,
  formFromPassport,
  issuesFor,
  PROVENANCE_LABEL,
  sourceHint,
  toUpdate,
} from "./form";
import { passport66, validation66, warning } from "./testFixtures";

describe("форма ⇄ payload", () => {
  it("круг без потерь", () => {
    const passport = passport66();
    const update = toUpdate(formFromPassport(passport), passport.version);
    expect(update).toEqual({
      passport_no: passport.passport_no, passport_date: passport.passport_date, payload: passport.payload, expected_version: 3,
    });
  });

  it("пустое число — null (возьмётся из справочника), запятая — дробная часть", () => {
    const form = formFromPassport(passport66());
    form.values.axis_offset_m = "";
    form.values.alpha_deg = "75,5";
    const payload = toUpdate(form, 3).payload;
    expect(payload.axis_offset_m).toBeNull();
    expect(payload.alpha_deg).toBe(75.5);
  });

  it("пустые строки ознакомления и согласований отбрасываются", () => {
    const form = formFromPassport(passport66());
    form.personnel = [...form.personnel, { name: " ", position: "" }];
    form.extra_approvals = ["маркшейдер", " "];
    const payload = toUpdate(form, 3).payload;
    expect(payload.personnel).toEqual([{ name: "Петров", position: "машинист" }]);
    expect(payload.extra_approvals).toEqual(["маркшейдер"]);
  });

  it("пустой допуск — 0,3 м", () => {
    const form = formFromPassport(passport66());
    form.values.tol_depth_m = "";
    expect(toUpdate(form, 3).payload.tol_depth_m).toBe(0.3);
  });

  it("не число — ошибка у поля", () => {
    const form = formFromPassport(passport66());
    form.values.gamma_deg = "шестьдесят";
    expect(formErrors(form)).toEqual({ gamma_deg: "Введите число." });
    expect(formErrors(formFromPassport(passport66()))).toEqual({});
  });

  it("пределы чисел — как в схеме API, по-русски", () => {
    const form = formFromPassport(passport66());
    form.values.alpha_deg = "25";
    form.values.gamma_deg = "95";
    form.values.tol_depth_m = "3";
    form.values.axis_offset_m = "-1";
    form.values.block_area_m2 = "0";
    expect(formErrors(form)).toEqual({
      alpha_deg: "От 30 до 90.",
      gamma_deg: "От 20 до 90.",
      tol_depth_m: "Больше 0 и не больше 2.",
      axis_offset_m: "От 0 до 5.",
      block_area_m2: "Больше 0.",
    });
  });

  it("№ и дата паспорта обязательны", () => {
    const form = formFromPassport(passport66());
    form.values.passport_no = " ";
    form.values.passport_date = "";
    expect(formErrors(form)).toEqual({ passport_no: "Заполните.", passport_date: "Заполните." });
  });

  it("поля и пределы длины — как в схеме API", () => {
    const fields = Object.fromEntries(FIELD_GROUPS.flatMap((group) => group.fields).map((field) => [field.key, field]));
    expect(fields.block).toMatchObject({ label: "Блок", maxLength: 40 });
    expect(fields.site_preparation).toMatchObject({ kind: "textarea", maxLength: 300 });
    expect(fields.site_code).toMatchObject({ kind: "reference", section: "sites" });
    expect(fields.rig_type_code).toMatchObject({ kind: "reference", section: "equipment_types" });
    expect(fields.profile_code).toMatchObject({ kind: "reference", section: "drill_passport_profiles" });
    expect(fields.alpha_deg).toMatchObject({ kind: "number", unit: "°" });
  });
});

describe("источники величин", () => {
  it("подписи происхождения", () => {
    expect(PROVENANCE_LABEL).toEqual({
      MANUAL_OVERRIDE: "вручную", REFERENCE: "справочник", DESIGN: "проект блока", CALCULATED: "расчёт",
    });
  });

  it("подсказка пустого поля — значение и источник", () => {
    expect(sourceHint("alpha_deg", validation66())).toBe("75° · справочник");
    expect(sourceHint("block_area_m2", validation66())).toBe("2 790 м² · проект блока");
    expect(sourceHint("w_max_m", validation66())).toBeNull();
    expect(sourceHint("alpha_deg", null)).toBeNull();
  });
});

describe("замечания у поля", () => {
  it("stakeout_names_invalid — у «Блока»", () => {
    const issues = [warning("stakeout_names_invalid", "block"), warning("w_max_missing", "w_max_m")];
    expect(issuesFor("block", issues).map((issue) => issue.code)).toEqual(["stakeout_names_invalid"]);
  });
});

describe("проверка первого ряда", () => {
  it("блок 66: s посчитан, Hs выше проекта, Wпред не задана", () => {
    const rows = checkRows(validation66([warning("bench_above_design", "bench_height_for_s_m"), warning("w_max_missing", "w_max_m")]));
    const byKey = Object.fromEntries(rows.map((row) => [row.key, row]));
    expect(byKey.s).toMatchObject({ value: "2,0 м", status: "ok" });
    expect(byKey.hs).toMatchObject({ value: "10,0 м", status: "warn", note: "вручную" });
    expect(byKey.h1).toMatchObject({ value: "11,7 м", status: "info" });
    expect(byKey.c).toMatchObject({ value: "0,8 м", note: "принято c_min" });
    expect(byKey.w).toMatchObject({ value: "5,14 м", status: "none" });
    expect(byKey.w_max).toMatchObject({ value: "—", status: "none", note: "не задана — проверка W пропущена" });
  });

  it("без α и γ s не посчитан", () => {
    const validation = validation66();
    validation.first_row_check = { ...validation.first_row_check, s_m: null, c_min_m: null, w_m: null };
    const s = checkRows(validation).find((row) => row.key === "s");
    expect(s).toMatchObject({ value: "—", status: "none" });
  });

  it("W больше Wпред — предупреждение", () => {
    const validation = validation66([warning("first_row_burden", "w_max_m")]);
    validation.first_row_check.w_max_m = 5;
    const w = checkRows(validation).find((row) => row.key === "w");
    expect(w?.status).toBe("warn");
  });

  it("W не больше Wпред — норма", () => {
    const validation = validation66();
    validation.first_row_check.w_max_m = 6;
    expect(checkRows(validation).find((row) => row.key === "w")?.status).toBe("ok");
  });
});

describe("выпуск ревизии", () => {
  it("отметка «просмотрено» — у текста предупреждения: новый текст того же кода — не отмечен", () => {
    const before = { ...warning("first_row_burden"), message: "W 7,2 м больше 7,0 м" };
    const after = { ...warning("first_row_burden"), message: "W 7,2 м больше 5,0 м" };
    expect(canRelease(validation66([before]), new Set([ackKey(before)]))).toBe(true);
    expect(canRelease(validation66([after]), new Set([ackKey(before)]))).toBe(false);
  });

  it("ошибка блокирует, предупреждения — только отмеченные", () => {
    const error: DrillPassportIssue = { level: "error", code: "slope_angles_required", message: "", path: "alpha_deg" };
    expect(canRelease(validation66([error]), new Set())).toBe(false);
    const two = validation66([warning("w_max_missing"), warning("axis_offset_missing")]);
    expect(canRelease(two, new Set([ackKey(two.issues[0])]))).toBe(false);
    expect(canRelease(two, new Set(two.issues.map(ackKey)))).toBe(true);
    expect(canRelease(null, new Set())).toBe(false);
  });
});
