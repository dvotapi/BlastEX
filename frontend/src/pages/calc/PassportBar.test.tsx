// @vitest-environment jsdom
import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../../api/endpoints", () => ({
  api: {
    economics: {
      technicalPassports: vi.fn(),
      referenceSnapshot: vi.fn(),
      createTechnicalPassport: vi.fn(),
      deleteTechnicalPassport: vi.fn(),
    },
  },
}));

import { api } from "../../api/endpoints";
import { PassportBar } from "./PassportBar";
import type { EconomicsReferenceSnapshot } from "../../types/economics";
import type { BlastGeometryResponse } from "../../types";
import type { TechnicalPassport } from "../../types/blockEconomics";

afterEach(cleanup);

const DRESVA = 'карьер месторождения "Дресьва"';
const DAYKA = 'карьер месторождения "Рассохинская Дайка"';

function snapshot(): EconomicsReferenceSnapshot {
  const site = (code: string, name: string) => ({
    code,
    name,
    payload: {},
    is_active: true,
    valid_from: null,
    valid_to: null,
    source: "test",
    comment: "",
    revision: 1,
  });
  return {
    revision_id: "REV-1",
    published_at: "2026-09-01T00:00:00Z",
    published_by: "tester",
    sections: { sites: [site("SITE_DRESVA", DRESVA), site("SITE_DAYKA", DAYKA)] },
    section_catalog: [],
    group_catalog: [],
  };
}

function passport(id: string, name: string, siteCode: string): TechnicalPassport {
  return {
    id,
    organization_id: "default",
    site_code: siteCode,
    object_name: name,
    version_no: 1,
    previous_passport_id: null,
    reference_revision_id: "REV-1",
    formula_version: "blast-geometry-v1",
    input_snapshot: {},
    selected_variant: {},
    block_snapshot: {},
    physical: { rock_volume_m3: 30000, explosive_kg: 20727 },
    lineage: {},
    created_at: "2026-09-05T00:00:00Z",
    created_by: "tester",
  };
}

const GEOMETRY = {
  label: "Ø 140 мм",
  block: {
    block_volume_m3: 30000,
    total_charge_mass_kg: 20727,
    total_holes: 189,
    drilling_footage_m: 2079,
    specific_q_kg_m3: 0.69,
  },
} as unknown as BlastGeometryResponse;

function setup(objectName = DRESVA) {
  render(
    <PassportBar
      variants={[{ key: "left", label: "Вариант 1", geometry: GEOMETRY }]}
      objectName={objectName}
      onOpenEconomics={vi.fn()}
    />,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(api.economics.referenceSnapshot).mockResolvedValue(snapshot());
  vi.mocked(api.economics.technicalPassports).mockResolvedValue([
    passport("P-1", "Блок 4", "SITE_DRESVA"),
  ]);
});

describe("PassportBar", () => {
  it("объект работ не выбирается здесь — он берётся из шапки страницы", async () => {
    setup();
    await screen.findByText("Блок 4");
    expect(screen.queryByLabelText("Объект работ")).toBeNull();
    expect(screen.getByText(new RegExp(`по объекту «${DRESVA}»`))).toBeTruthy();
  });

  it("список запрашивается по коду объекта из шапки", async () => {
    setup();
    await waitFor(() =>
      expect(api.economics.technicalPassports).toHaveBeenCalledWith("SITE_DRESVA"),
    );
  });

  it("новый паспорт сохраняется на объект из шапки", async () => {
    vi.mocked(api.economics.createTechnicalPassport).mockResolvedValue(
      passport("P-2", "Новый блок", "SITE_DAYKA"),
    );
    setup(DAYKA);
    await screen.findByRole("button", { name: "Сохранить паспорт" });
    await userEvent.click(screen.getByRole("button", { name: "Сохранить паспорт" }));
    await waitFor(() =>
      expect(api.economics.createTechnicalPassport).toHaveBeenCalledWith(
        expect.objectContaining({ site_code: "SITE_DAYKA" }),
      ),
    );
  });

  it("объекта шапки нет в справочнике — сохранять некуда, и это видно", async () => {
    setup("объект вне справочника");
    await screen.findByRole("alert");
    expect(screen.getByRole("button", { name: "Сохранить паспорт" }).hasAttribute("disabled")).toBe(
      true,
    );
    expect(api.economics.technicalPassports).not.toHaveBeenCalled();
  });

  it("удаление убирает паспорт из списка после подтверждения", async () => {
    vi.mocked(api.economics.deleteTechnicalPassport).mockResolvedValue(undefined);
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(true);
    setup();
    const row = (await screen.findByText("Блок 4")).closest(".passport-list-row") as HTMLElement;
    await userEvent.click(within(row).getByRole("button", { name: "Удалить" }));
    await waitFor(() => expect(screen.queryByText("Блок 4")).toBeNull());
    expect(api.economics.deleteTechnicalPassport).toHaveBeenCalledWith("P-1");
    confirm.mockRestore();
  });

  it("отказ в подтверждении оставляет паспорт на месте", async () => {
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(false);
    setup();
    const row = (await screen.findByText("Блок 4")).closest(".passport-list-row") as HTMLElement;
    await userEvent.click(within(row).getByRole("button", { name: "Удалить" }));
    expect(api.economics.deleteTechnicalPassport).not.toHaveBeenCalled();
    expect(screen.getByText("Блок 4")).toBeTruthy();
    confirm.mockRestore();
  });

  it("ошибка удаления показывается, а строка остаётся", async () => {
    vi.mocked(api.economics.deleteTechnicalPassport).mockRejectedValue(
      new Error("Технический паспорт P-1 удалён."),
    );
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(true);
    setup();
    const row = (await screen.findByText("Блок 4")).closest(".passport-list-row") as HTMLElement;
    await userEvent.click(within(row).getByRole("button", { name: "Удалить" }));
    await screen.findByText("Технический паспорт P-1 удалён.");
    expect(screen.getByText("Блок 4")).toBeTruthy();
    confirm.mockRestore();
  });
});
