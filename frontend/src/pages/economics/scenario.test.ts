import { describe, expect, it } from "vitest";

import { draftFromDefaults, draftFromRun, isDirty, markSaved, scenarioLabel } from "./scenario";
import type { BlockEconomics, EconomicsRun, EconomicsRunSummary, ModelParameters } from "../../types/blockEconomics";

function baseParameters(): ModelParameters {
  return {
    package_code: "DRILL_AND_BLAST",
    site_code: "SITE_MAIN",
    reference_revision_id: "",
    unit_plan_volume_m3: "600000",
    rig_code: "RIG_JK830",
    rig_plan_shifts: "40",
    szm_code: "SZM_12T",
    delivery_truck_code: "TRUCK_3T",
    emulsion_truck_code: null,
    machine_plan_shifts: {},
    crew: [],
    services: [],
    drilling_executor: "OWN",
    subcontract_rate_code: null,
    subcontract_rate_rub: null,
    nomenclature: {},
    electric_detonators_qty: "0",
    overhead_rate: null,
    target_margin_rate: null,
    vat_rate: null,
  };
}

function baseRun(overrides: Partial<EconomicsRun> = {}): EconomicsRun {
  return {
    id: "run-1",
    organization_id: "org-1",
    name: "Сценарий 2",
    technical_passport_id: "passport-1",
    package_code: "DRILL_AND_BLAST",
    reference_revision_id: "rev-1",
    // На бэкенде это ModelParametersSchema.to_dict(); в тесте достаточно
    // реального набора полей ModelParameters, приведённого к контракту поля.
    parameters: baseParameters() as unknown as Record<string, unknown>,
    result: {} as BlockEconomics,
    created_at: "2026-01-01T00:00:00Z",
    created_by: "user-1",
    ...overrides,
  };
}

describe("draftFromDefaults", () => {
  it("новый черновик из умолчаний считается несохранённым", () => {
    expect(isDirty(draftFromDefaults("Вариант 1", baseParameters()))).toBe(true);
  });

  it("не привязан ни к какому прогону", () => {
    const draft = draftFromDefaults("Вариант 1", baseParameters());
    expect(draft.sourceRunId).toBeNull();
    expect(draft.name).toBe("Вариант 1");
  });
});

describe("draftFromRun", () => {
  it("черновик из прогона чист, пока параметры не тронули", () => {
    const draft = draftFromRun(baseRun(), "Сценарий 2");
    expect(isDirty(draft)).toBe(false);
    expect(isDirty({ ...draft, parameters: { ...draft.parameters, vat_rate: 0 } })).toBe(true);
  });

  it("привязан к прогону-источнику и берёт имя из аргумента, а не из прогона", () => {
    const run = baseRun({ id: "run-42", name: "Сохранённое имя прогона" });
    const draft = draftFromRun(run, "Мой черновик");
    expect(draft.sourceRunId).toBe("run-42");
    expect(draft.name).toBe("Мой черновик");
  });

  it("параметры черновика равны параметрам прогона по значению", () => {
    const run = baseRun();
    const draft = draftFromRun(run, "Сценарий 2");
    expect(draft.parameters).toEqual(baseParameters());
  });

  it("нормализует отсутствующие поля субподряда в null, а не оставляет undefined", () => {
    // Прогон, сохранённый до появления полей субподряда бурения: ключей нет
    // вовсе в сериализованных параметрах — как если бы старая запись пришла
    // с бэкенда без них.
    const legacyParameters = baseParameters() as unknown as Record<string, unknown>;
    delete legacyParameters.subcontract_rate_code;
    delete legacyParameters.subcontract_rate_rub;
    const run = baseRun({ parameters: legacyParameters });

    const draft = draftFromRun(run, "Старый прогон");

    expect(draft.parameters.subcontract_rate_code).toBeNull();
    expect(draft.parameters.subcontract_rate_rub).toBeNull();
  });

  it("настоящее значение поля субподряда перекрывает дефолт null", () => {
    const run = baseRun({
      parameters: { ...baseParameters(), subcontract_rate_code: "RATE_A" } as unknown as Record<string, unknown>,
    });

    const draft = draftFromRun(run, "Сценарий с субподрядом");

    expect(draft.parameters.subcontract_rate_code).toBe("RATE_A");
    expect(draft.parameters.subcontract_rate_rub).toBeNull();
  });
});

describe("markSaved", () => {
  it("после сохранения черновик перестаёт быть грязным и привязывается к новому прогону", () => {
    const dirty = draftFromDefaults("Вариант 1", baseParameters());
    const saved = markSaved(dirty, "run-99");
    expect(saved.sourceRunId).toBe("run-99");
    expect(isDirty(saved)).toBe(false);
  });

  it("дальнейшая правка параметров снова делает черновик грязным", () => {
    const saved = markSaved(draftFromDefaults("Вариант 1", baseParameters()), "run-99");
    const edited = { ...saved, parameters: { ...saved.parameters, vat_rate: 0.2 } };
    expect(isDirty(edited)).toBe(true);
  });
});

describe("scenarioLabel", () => {
  const runs: EconomicsRunSummary[] = [
    {
      id: "run-1",
      name: "Сценарий 2",
      technical_passport_id: "passport-1",
      package_code: "DRILL_AND_BLAST",
      reference_revision_id: "rev-1",
      created_at: "2026-01-01T00:00:00Z",
      created_by: "user-1",
      price_per_m3: {},
    },
  ];

  it("чистый черновик сохранённого прогона показывает имя прогона без пометки", () => {
    const draft = draftFromRun(baseRun(), "Сценарий 2");
    expect(scenarioLabel(draft, runs)).toBe("Сценарий 2");
  });

  it("тронутый черновик получает пометку «· черновик»", () => {
    const draft = draftFromRun(baseRun(), "Сценарий 2");
    const dirty = { ...draft, parameters: { ...draft.parameters, vat_rate: 0.2 } };
    expect(scenarioLabel(dirty, runs)).toBe("Сценарий 2 · черновик");
  });

  it("новый черновик без прогона показывает своё имя с пометкой", () => {
    const draft = draftFromDefaults("Вариант 1", baseParameters());
    expect(scenarioLabel(draft, runs)).toBe("Вариант 1 · черновик");
  });

  it("прогон-источник не найден в списке — используется имя черновика", () => {
    const draft = draftFromRun(baseRun({ id: "run-deleted" }), "Открыт из истории");
    expect(scenarioLabel(draft, runs)).toBe("Открыт из истории");
  });
});
