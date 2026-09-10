import { describe, expect, it } from "vitest";

import { draftFromDefaults, draftFromRun, isDirty, markSaved, markSavedIfCurrent, scenarioLabel } from "./scenario";
import type { BlockEconomics, EconomicsRun, ModelParameters } from "../../types/blockEconomics";

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

  it("подставляет пустые коллекции вместо полей, которых нет в старом прогоне", () => {
    // Прогон эпохи до конструктора сметы: списочных полей в нём нет вовсе.
    // Раньше они уезжали в черновик как `undefined` и роняли всю страницу на
    // первом же обращении к длине списка (`ServicesPanel`).
    const legacyParameters = baseParameters() as unknown as Record<string, unknown>;
    delete legacyParameters.services;
    delete legacyParameters.crew;
    delete legacyParameters.machine_plan_shifts;
    delete legacyParameters.nomenclature;
    delete legacyParameters.emulsion_truck_code;

    const draft = draftFromRun(baseRun({ parameters: legacyParameters }), "Старый прогон");

    expect(draft.parameters.services).toEqual([]);
    expect(draft.parameters.crew).toEqual([]);
    expect(draft.parameters.machine_plan_shifts).toEqual({});
    expect(draft.parameters.nomenclature).toEqual({});
    expect(draft.parameters.emulsion_truck_code).toBeNull();
  });

  it("берёт недостающее поле из каталога умолчаний, когда он передан", () => {
    const legacyParameters = baseParameters() as unknown as Record<string, unknown>;
    delete legacyParameters.crew;
    delete legacyParameters.unit_plan_volume_m3;
    const fallback: ModelParameters = {
      ...baseParameters(),
      crew: [{ position_code: "POS_MASTER", headcount: "1", shifts_per_block: null }],
      unit_plan_volume_m3: "750000",
    };

    const draft = draftFromRun(baseRun({ parameters: legacyParameters }), "Старый прогон", fallback);

    expect(draft.parameters.crew).toEqual(fallback.crew);
    expect(draft.parameters.unit_plan_volume_m3).toBe("750000");
  });

  it("явный null в прогоне не подменяется значением из умолчаний", () => {
    // `rig_plan_shifts: null` означает «считать по нормативу» — это осознанный
    // выбор сметчика, а не пропуск поля.
    const fallback: ModelParameters = { ...baseParameters(), rig_plan_shifts: "40" };
    const run = baseRun({
      parameters: { ...baseParameters(), rig_plan_shifts: null } as unknown as Record<string, unknown>,
    });

    const draft = draftFromRun(run, "Сценарий по нормативу", fallback);

    expect(draft.parameters.rig_plan_shifts).toBeNull();
  });

  it("переустанавливает ревизию справочников на актуальную, а не тянет историческую из прогона", () => {
    // Прогон посчитан и сохранён на исторической ревизии "rev-old" — черновик,
    // открытый из него для дальнейшей правки, должен считать на актуальной
    // ревизии (пустая строка), а не на той, что была зафиксирована в прогоне.
    const run = baseRun({
      parameters: { ...baseParameters(), reference_revision_id: "rev-old" } as unknown as Record<string, unknown>,
    });

    const draft = draftFromRun(run, "Сценарий с исторической ревизией");

    expect(draft.parameters.reference_revision_id).toBe("");
    expect(isDirty(draft)).toBe(false);
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

describe("markSavedIfCurrent", () => {
  it("помечает сохранённым, если параметры не изменились с момента отправки", () => {
    const draft = draftFromDefaults("Вариант 1", baseParameters());
    const result = markSavedIfCurrent(draft, "run-99", draft.parameters);
    expect(result.sourceRunId).toBe("run-99");
    expect(isDirty(result)).toBe(false);
  });

  it("не помечает savedKey (но привязывает sourceRunId), если параметры изменились после отправки", () => {
    const draft = draftFromDefaults("Вариант 1", baseParameters());
    const submittedParameters = draft.parameters;
    // Сметчик поправил черновик, пока сохранение летело на сервер.
    const edited = { ...draft, parameters: { ...draft.parameters, vat_rate: 0.2 } };
    const result = markSavedIfCurrent(edited, "run-99", submittedParameters);
    expect(result.sourceRunId).toBe("run-99");
    // savedKey не обновился на снимок отправленных параметров — черновик
    // остаётся «грязным» относительно реально сохранённого прогона.
    expect(isDirty(result)).toBe(true);
  });
});

describe("scenarioLabel", () => {
  it("чистый черновик сохранённого прогона показывает имя без пометки", () => {
    const draft = draftFromRun(baseRun(), "Сценарий 2");
    expect(scenarioLabel(draft)).toBe("Сценарий 2");
  });

  it("тронутый черновик получает пометку «· черновик»", () => {
    const draft = draftFromRun(baseRun(), "Сценарий 2");
    const dirty = { ...draft, parameters: { ...draft.parameters, vat_rate: 0.2 } };
    expect(scenarioLabel(dirty)).toBe("Сценарий 2 · черновик");
  });

  it("новый черновик без прогона показывает своё имя с пометкой", () => {
    const draft = draftFromDefaults("Вариант 1", baseParameters());
    expect(scenarioLabel(draft)).toBe("Вариант 1 · черновик");
  });

  it("переименованный черновик прогона показывает новое имя, а не имя прогона", () => {
    // Прогон в базе остаётся под своим именем — переименование касается
    // только открытого из него черновика, и в списке сценариев должно быть
    // видно именно оно, иначе действие выглядит несработавшим.
    const draft = draftFromRun(baseRun({ name: "Сохранённое имя прогона" }), "Сохранённое имя прогона");
    expect(scenarioLabel({ ...draft, name: "Новое имя" })).toBe("Новое имя");
  });
});
