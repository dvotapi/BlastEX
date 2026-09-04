import { describe, expect, it } from "vitest";
import { settingsPatch } from "./publicSettings";
import type { PublicSyncSettings } from "../../types/economics";

function settings(overrides: Partial<PublicSyncSettings> = {}): PublicSyncSettings {
  return {
    exchange_enabled: false,
    mirror_sections: { rocks: false, explosives: false, positions: false },
    mirrorable_sections: ["rocks", "explosives", "positions"],
    mapped_sections: ["counterparties", "sites"],
    ...overrides,
  };
}

describe("settingsPatch", () => {
  it("включает обмен, не трогая зеркала", () => {
    const current = settings({ mirror_sections: { rocks: true, explosives: false, positions: false } });
    expect(settingsPatch(current, { exchange_enabled: true })).toEqual({
      exchange_enabled: true,
      mirror_sections: { rocks: true, explosives: false, positions: false },
    });
  });

  it("выключает обмен, не трогая зеркала", () => {
    const current = settings({
      exchange_enabled: true,
      mirror_sections: { rocks: true, explosives: true, positions: false },
    });
    expect(settingsPatch(current, { exchange_enabled: false })).toEqual({
      exchange_enabled: false,
      mirror_sections: { rocks: true, explosives: true, positions: false },
    });
  });

  it("включает раздел, оставляя остальные как были", () => {
    const current = settings({
      exchange_enabled: true,
      mirror_sections: { rocks: false, explosives: true, positions: false },
    });
    expect(settingsPatch(current, { section: "rocks", enabled: true })).toEqual({
      exchange_enabled: true,
      mirror_sections: { rocks: true, explosives: true, positions: false },
    });
  });

  it("выключает раздел", () => {
    const current = settings({
      exchange_enabled: true,
      mirror_sections: { rocks: true, explosives: true, positions: false },
    });
    expect(settingsPatch(current, { section: "explosives", enabled: false })).toEqual({
      exchange_enabled: true,
      mirror_sections: { rocks: true, explosives: false, positions: false },
    });
  });

  it("игнорирует раздел вне списка доступных для зеркала", () => {
    const current = settings({ exchange_enabled: true });
    expect(settingsPatch(current, { section: "sites", enabled: true })).toEqual({
      exchange_enabled: true,
      mirror_sections: { rocks: false, explosives: false, positions: false },
    });
  });

  it("присылает все доступные разделы, даже если сервер не назвал их состояние", () => {
    const current = settings({ mirror_sections: { rocks: true } });
    expect(settingsPatch(current, { section: "positions", enabled: true })).toEqual({
      exchange_enabled: false,
      mirror_sections: { rocks: true, explosives: false, positions: true },
    });
  });

  it("не переносит в тело разделы, которых нет среди доступных", () => {
    const current = settings({ mirror_sections: { rocks: true, sites: true } });
    expect(settingsPatch(current, {}).mirror_sections).toEqual({
      rocks: true,
      explosives: false,
      positions: false,
    });
  });
});
