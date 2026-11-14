import { describe, expect, it } from "vitest";
import type { DrillPassportIssue } from "../../../types/drillPassport";
import {
  ackKey,
  applyProfileWorkOrder,
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

  it("допуски съёмки: заданные — круг без потерь, пустые — не отправляются", () => {
    const passport = passport66();
    passport.payload = { ...passport.payload, tol_angle_deg: 1.5, tol_burden_pct: 7, tol_spacing_pct: 10 };
    const form = formFromPassport(passport);
    expect([form.values.tol_angle_deg, form.values.tol_burden_pct, form.values.tol_spacing_pct]).toEqual(["1,5", "7", "10"]);
    expect(toUpdate(form, 3).payload).toEqual(passport.payload);
    form.values.tol_angle_deg = " ";
    const payload = toUpdate(form, 3).payload;
    expect("tol_angle_deg" in payload).toBe(false);
    expect(payload.tol_burden_pct).toBe(7);
    expect(Object.keys(toUpdate(formFromPassport(passport66()), 3).payload)).not.toContain("tol_spacing_pct");
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
    form.values = { ...formFromPassport(passport66()).values, tol_angle_deg: "10,5", tol_burden_pct: "0", tol_spacing_pct: "51" };
    expect(formErrors(form)).toEqual({
      tol_angle_deg: "Больше 0 и не больше 10.",
      tol_burden_pct: "Больше 0 и не больше 50.",
      tol_spacing_pct: "Больше 0 и не больше 50.",
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
    expect(fields.profile_code.hint).toContain("порядок работ");
    expect(fields.alpha_deg).toMatchObject({ kind: "number", unit: "°" });
    // c и Wпред — из проекта блока, в форме их нет (доработки 10.11.2026).
    expect(fields.first_row_offset_m).toBeUndefined();
    expect(fields.w_max_m).toBeUndefined();
    // Даты бурения заполняются сами в ISO — в форме выбор даты (10.11.2026).
    expect(fields.drilling_start).toMatchObject({ kind: "date" });
    expect(fields.drilling_end).toMatchObject({ kind: "date", label: "Окончание бурения (план)" });
  });
});

describe("порядок работ из профиля", () => {
  it("непустые тексты профиля заменяют поля, пустые — не трогают", () => {
    const form = formFromPassport(passport66());
    const next = applyProfileWorkOrder(form, { power_lines: "ВЛ 6 кВ", stakeout: " ", safety_basis: "не поле формы" });
    expect(next.values.power_lines).toBe("ВЛ 6 кВ");
    expect(next.values.stakeout).toBe(form.values.stakeout);
    expect(next.values.drilling_order).toBe(form.values.drilling_order);
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
    expect(sourceHint("axis_offset_m", { ...validation66(), provenance: {} })).toBeNull();
    expect(sourceHint("alpha_deg", null)).toBeNull();
  });
});

describe("замечания у поля", () => {
  it("stakeout_names_invalid — у «Блока»", () => {
    const issues = [warning("stakeout_names_invalid", "block"), warning("w_max_missing", "holes")];
    expect(issuesFor("block", issues).map((issue) => issue.code)).toEqual(["stakeout_names_invalid"]);
  });
});

describe("проверка первого ряда", () => {
  const byKey = (validation: ReturnType<typeof validation66>) =>
    Object.fromEntries(checkRows(validation).map((row) => [row.key, row]));

  it("три строки: s, первый ряд от бровки, ЛСПП — по проекту, без ручных c и Wпред", () => {
    const rows = checkRows(validation66([warning("first_row_burden")]));
    expect(rows.map((row) => row.key)).toEqual(["s", "c", "w"]);
    const keyed = byKey(validation66([warning("first_row_burden")]));
    expect(keyed.s).toMatchObject({ value: "2,0 м", status: "ok", note: "печатается в паспорте" });
    expect(keyed.c).toMatchObject({ value: "1,7…3,1 м", status: "ok", note: "нужно не меньше 0,8 м (s − e)" });
    expect(keyed.w).toMatchObject({ value: "до 5,94 м", status: "warn", note: "допустимая 3,81 м (W проекта + 3 %)" });
  });

  it("Hs — строкой только при предупреждении о высоте уступа", () => {
    const keyed = byKey(validation66([warning("bench_above_design")]));
    expect(keyed.hs).toMatchObject({ value: "11,7 м", status: "warn", note: "Hs 10,0 м · вручную" });
    expect(byKey(validation66()).hs).toBeUndefined();
  });

  it("устья ближе c_min — предупреждение", () => {
    expect(byKey(validation66([warning("first_row_too_close")])).c.status).toBe("warn");
  });

  it("ЛСПП в допуске — норма", () => {
    expect(byKey(validation66()).w.status).toBe("ok");
  });

  it("без бровки c и W не измерены", () => {
    const validation = validation66([warning("first_row_not_measured")]);
    validation.first_row_check = { ...validation.first_row_check, c_m: null, c_max_m: null, w_m: null, w_max_m: null };
    const keyed = byKey(validation);
    expect(keyed.c).toMatchObject({ value: "—", status: "none", note: "нет бровки — не измерить" });
    expect(keyed.w).toMatchObject({ value: "—", status: "none", note: "нет бровки — не измерить" });
  });

  it("W проекта не задана — ЛСПП без допуска", () => {
    const validation = validation66([warning("w_max_missing")]);
    validation.first_row_check.w_max_m = null;
    expect(byKey(validation).w).toMatchObject({ status: "none", note: "W в проекте не задана — не проверить" });
  });

  it("бровка есть, линии подошвы нет — ЛСПП «не посчитана», а не «нет бровки»", () => {
    const validation = validation66([warning("first_row_burden_not_measured")]);
    validation.first_row_check = { ...validation.first_row_check, w_m: null, w_max_m: null };
    expect(byKey(validation).w).toMatchObject({ value: "—", status: "none", note: "нет линии подошвы — не посчитать" });
  });

  it("скважины в откосе — предупреждение у ЛСПП", () => {
    const keyed = byKey(validation66([warning("first_row_beyond_toe")]));
    expect(keyed.w).toMatchObject({ status: "warn" });
    expect(keyed.w.note).toContain("выходят в откос");
  });

  it("без α и γ s не посчитан", () => {
    const validation = validation66();
    validation.first_row_check = { ...validation.first_row_check, s_m: null, c_min_m: null };
    expect(byKey(validation).s).toMatchObject({ value: "—", status: "none" });
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
