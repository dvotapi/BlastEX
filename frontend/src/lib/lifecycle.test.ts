import { describe, expect, it } from "vitest";
import { SURVEY_STAGE_LABELS, surveyStage } from "./lifecycle";
import type { SurveyApplication } from "../types/design";

describe("surveyStage", () => {
  it("нет записей — preliminary, есть — surveyed", () => {
    expect(surveyStage({})).toBe("preliminary");
    expect(surveyStage({ survey_applications: [] })).toBe("preliminary");
    expect(surveyStage({ survey_applications: [{} as SurveyApplication] })).toBe("surveyed");
    expect(SURVEY_STAGE_LABELS).toEqual({ preliminary: "предварительный", surveyed: "по съёмке" });
  });
});
