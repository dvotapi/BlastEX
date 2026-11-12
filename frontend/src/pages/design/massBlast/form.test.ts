import { describe, expect, it } from "vitest";
import { formErrors, formFromProject, parseNumber, toInput } from "./form";
import { tabForIssue } from "./MassBlastDialog";
import { projectV2 } from "./testFixtures";

describe("форма проекта МВ v2", () => {
  it("числа с запятой; пустое поле — не задано, а не 0", () => {
    expect(parseNumber("1,25")).toBe(1.25);
    expect(parseNumber(" 1 200,5 ")).toBe(1200.5);
    expect(parseNumber("")).toBeNull();
    expect(parseNumber("абв")).toBe("invalid");
  });

  it("проект → форма → payload сохраняет поля и версию", () => {
    const project = projectV2({
      explosives: { bit_mm: 140, reaming_k: 1.03, q_tp_kg_m3: null, initiation: "НСИ" },
      safety_overrides: { k_ground: 8, frost: false },
      safety_plan: { manual_zones: { people: { value: 800, reason: "по ТП" } } },
      layout_points: [{ kind: "blast_station", ref: "", x: 10.5, y: -3, label: "" }],
    });
    const form = formFromProject(project);
    expect(form.explosives.reaming_k).toBe("1,03");
    expect(form.overrides).toEqual({ k_ground: "8", frost: "false" });
    const input = toInput(form, project);
    expect(input.context_version).toBe(2);
    expect(input.expected_version).toBe(3);
    expect(input.explosives).toMatchObject({ bit_mm: 140, reaming_k: 1.03, q_tp_kg_m3: null, initiation: "НСИ" });
    expect(input.safety_overrides).toEqual({ k_ground: 8, frost: false });
    expect(input.safety_plan).toEqual({ manual_zones: { people: { value: 800, reason: "по ТП" } } });
    expect(input.layout_points).toEqual([{ kind: "blast_station", ref: "", x: 10.5, y: -3, label: "" }]);
    // Поля, которых окно не правит, уходят как есть.
    expect(input.signal_plan).toEqual({ profile_code: "STANDARD" });
    expect(input.reference_revision_id).toBe("ref-1");
    expect(input.responsibilities.map((item) => item.account_email)).toEqual(["lead@example.test", "store@example.test"]);
  });

  it("пустой ручной коэффициент и пустая согласующая строка не уходят", () => {
    const project = projectV2();
    const form = formFromProject(project);
    form.overrides.k_ground = "";
    form.requisites.agreements[0] = { position: "маркшейдер", name: "Маркшейдеров М. М." };
    form.zones.people = { value: "", reason: "" };
    const input = toInput(form, project);
    expect(input.safety_overrides).toEqual({});
    expect(input.requisites.agreements).toEqual([{ position: "маркшейдер", name: "Маркшейдеров М. М." }]);
    expect(input.safety_plan).toEqual({});
  });

  it("ошибки ввода: не число, зона без причины, повтор постов, учётка без человека", () => {
    const form = formFromProject(projectV2());
    form.explosives.bit_mm = "сто";
    form.zones.people = { value: "800", reason: "" };
    form.guard_posts.push({ code: "1", location: "ещё", responsible_employee_code: "", notes: "" });
    form.approvals.blast_manager.name = "";
    const errors = formErrors(form);
    expect(errors["explosives.bit_mm"]).toBe("Введите число");
    expect(errors["safety_plan.manual_zones.people"]).toBe("Укажите причину");
    expect(errors.guard_posts).toBe("Номера постов повторяются");
    expect(errors["responsibilities.blast_manager"]).toMatch("Ф. И. О.");
  });

  it("замечание ведёт на вкладку своего поля", () => {
    const issue = (path: string, code = "x") => ({ level: "error" as const, code, message: "", path });
    expect(tabForIssue(issue("requisites.customer_approver"))).toBe("requisites");
    expect(tabForIssue(issue("blocks[0].technical_calculation"))).toBe("explosives");
    expect(tabForIssue(issue("blocks[0].safety"))).toBe("safety");
    expect(tabForIssue(issue("blocks[0]"))).toBe("blocks");
    expect(tabForIssue(issue("layout_points[2]"))).toBe("posts");
    expect(tabForIssue(issue("responsibilities"))).toBe("personnel");
    expect(tabForIssue(issue("", "blast_time_missing"))).toBe("requisites");
    expect(tabForIssue(issue("zones.people"))).toBe("safety");
    expect(tabForIssue(issue("attachments"))).toBe("documents");
  });
});
