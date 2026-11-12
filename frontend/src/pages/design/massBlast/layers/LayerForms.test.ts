import { describe, expect, it } from "vitest";
import { layer } from "../testFixtures";
import { draftFromPayload, payloadFromDraft } from "./LayerForms";

describe("ручной ввод слоёв", () => {
  it("отказы — по запятой, точке с запятой или строке; пробел внутри кода блока сохраняется", () => {
    const execution = layer({ kind: "EXECUTION", payload: { misfired_holes: [], hole_notes: {} } });
    const draft = { ...draftFromPayload(execution), misfired_text: "66 север:1, 66 север:12;\n67:3" };
    expect(payloadFromDraft("EXECUTION", draft).payload.misfired_holes).toEqual(["66 север:1", "66 север:12", "67:3"]);
  });

  it("запас наряда: пустое не уходит, запятая — десятичная, минус — ошибка", () => {
    const draft = { ...draftFromPayload(layer()), reserve: { a: "1,5", b: "", c: "-2" } };
    const { payload, errors } = payloadFromDraft("NARYAD", draft);
    expect(payload.reserve).toEqual({ a: 1.5 });
    expect(errors["reserve:c"]).toBe("Число не меньше нуля");
  });
});
