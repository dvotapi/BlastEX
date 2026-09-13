// @vitest-environment jsdom
import { cleanup, render, screen, waitFor } from "@testing-library/react";
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

function site(code: string, name: string, isActive = true) {
  return {
    code,
    name,
    payload: {},
    is_active: isActive,
    valid_from: null,
    valid_to: null,
    source: "test",
    comment: "",
    revision: 1,
  };
}

function snapshot(
  sites = [site("SITE_DRESVA", DRESVA), site("SITE_DAYKA", DAYKA)],
): EconomicsReferenceSnapshot {
  return {
    revision_id: "REV-1",
    published_at: "2026-09-01T00:00:00Z",
    published_by: "tester",
    sections: { sites },
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

function setup(objectName = DRESVA, onOpenEconomics = vi.fn()) {
  render(
    <PassportBar
      variants={[{ key: "left", label: "Вариант 1", geometry: GEOMETRY }]}
      objectName={objectName}
      onOpenEconomics={onOpenEconomics}
    />,
  );
  return { onOpenEconomics };
}

/** Сохранённый паспорт в выпадающем списке: «название · масса ВВ». */
const findPassport = (name: string) => screen.findByRole("option", { name: new RegExp(`^${name} ·`) });
const queryPassport = (name: string) => screen.queryByRole("option", { name: new RegExp(`^${name} ·`) });

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
    await findPassport("Блок 4");
    expect(screen.queryByLabelText("Объект работ")).toBeNull();
    expect(screen.getByText(/В паспорт пойдёт «Вариант 1»: 20 727 кг ВВ, 189 скважин/)).toBeTruthy();
  });

  it("список сохранённых паспортов показывает название и массу ВВ", async () => {
    setup();
    // `toLocaleString("ru-RU")` разделяет тысячи узким неразрывным пробелом.
    expect((await findPassport("Блок 4")).textContent?.replace(/\s/g, " ")).toBe("Блок 4 · 20 727 кг ВВ · 05.09.2026 · вер. 1");
    expect(screen.getByText("1 по объекту")).toBeTruthy();
  });

  it("«Экономика» и «Удалить» действуют на паспорт, выбранный в списке", async () => {
    vi.mocked(api.economics.technicalPassports).mockResolvedValue([
      passport("P-1", "Блок 4", "SITE_DRESVA"),
      passport("P-2", "Блок 5", "SITE_DRESVA"),
    ]);
    vi.mocked(api.economics.deleteTechnicalPassport).mockResolvedValue(undefined);
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(true);
    const { onOpenEconomics } = setup();
    await findPassport("Блок 5");
    await userEvent.selectOptions(screen.getByLabelText("Сохранённые паспорта"), "P-2");
    await userEvent.click(screen.getByRole("button", { name: "Экономика" }));
    expect(onOpenEconomics).toHaveBeenCalledWith("P-2");
    await userEvent.click(screen.getByRole("button", { name: "Удалить" }));
    await waitFor(() => expect(queryPassport("Блок 5")).toBeNull());
    expect(api.economics.deleteTechnicalPassport).toHaveBeenCalledWith("P-2");
    expect(queryPassport("Блок 4")).not.toBeNull();
    confirm.mockRestore();
  });

  it("пока схема пересчитывается, сохранить прошлый блок нельзя", async () => {
    render(
      <PassportBar
        variants={[{ key: "left", label: "Вариант 1", geometry: GEOMETRY, pending: true }]}
        objectName={DRESVA}
        onOpenEconomics={vi.fn()}
      />,
    );
    await findPassport("Блок 4");
    expect(screen.getByRole("button", { name: "Сохранить паспорт" })).toBeDisabled();
    expect(screen.getByText("Схема заряда пересчитывается…")).toBeTruthy();
    expect(screen.queryByText(/В паспорт пойдёт/)).toBeNull();
  });

  it("без сохранённых паспортов действия над ними выключены", async () => {
    vi.mocked(api.economics.technicalPassports).mockResolvedValue([]);
    setup();
    await waitFor(() => expect(api.economics.technicalPassports).toHaveBeenCalled());
    expect(screen.getByRole("button", { name: "Экономика" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Удалить" })).toBeDisabled();
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
    await findPassport("Блок 4");
    await userEvent.click(screen.getByRole("button", { name: "Удалить" }));
    await waitFor(() => expect(queryPassport("Блок 4")).toBeNull());
    expect(api.economics.deleteTechnicalPassport).toHaveBeenCalledWith("P-1");
    confirm.mockRestore();
  });

  it("отказ в подтверждении оставляет паспорт на месте", async () => {
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(false);
    setup();
    await findPassport("Блок 4");
    await userEvent.click(screen.getByRole("button", { name: "Удалить" }));
    expect(api.economics.deleteTechnicalPassport).not.toHaveBeenCalled();
    expect(queryPassport("Блок 4")).not.toBeNull();
    confirm.mockRestore();
  });

  it("закрытый объект-тёзка не перехватывает имя у действующего", async () => {
    // Объект закрыли и завели заново с тем же названием: в шапке остаётся
    // только действующий, паспорт обязан уйти на его код.
    vi.mocked(api.economics.referenceSnapshot).mockResolvedValue(
      snapshot([site("SITE_OLD", DRESVA, false), site("SITE_NEW", DRESVA)]),
    );
    setup();
    await waitFor(() =>
      expect(api.economics.technicalPassports).toHaveBeenCalledWith("SITE_NEW"),
    );
  });

  it("успешная загрузка списка гасит ошибку прошлого объекта", async () => {
    vi.mocked(api.economics.technicalPassports)
      .mockRejectedValueOnce(new Error("Не удалось загрузить паспорта."))
      .mockResolvedValueOnce([passport("P-9", "Блок Дайки", "SITE_DAYKA")]);
    const { rerender } = render(
      <PassportBar
        variants={[{ key: "left", label: "Вариант 1", geometry: GEOMETRY }]}
        objectName={DRESVA}
        onOpenEconomics={vi.fn()}
      />,
    );
    await screen.findByText("Не удалось загрузить паспорта.");
    rerender(
      <PassportBar
        variants={[{ key: "left", label: "Вариант 1", geometry: GEOMETRY }]}
        objectName={DAYKA}
        onOpenEconomics={vi.fn()}
      />,
    );
    await findPassport("Блок Дайки");
    expect(screen.queryByText("Не удалось загрузить паспорта.")).toBeNull();
  });

  it("пустой справочник объектов — объекта шапки нет, и это сказано", async () => {
    // Активных объектов нет: шапка всё равно показывает объект Cost V1 по
    // умолчанию, поэтому молчать нельзя — сохранять паспорт некуда.
    vi.mocked(api.economics.referenceSnapshot).mockResolvedValue(snapshot([]));
    setup();
    await screen.findByRole("alert");
    expect(screen.getByRole("button", { name: "Сохранить паспорт" }).hasAttribute("disabled")).toBe(
      true,
    );
  });

  it("смена объекта во время сохранения не подмешивает паспорт в чужой список", async () => {
    let resolveCreate: (value: TechnicalPassport) => void = () => {};
    vi.mocked(api.economics.createTechnicalPassport).mockReturnValue(
      new Promise<TechnicalPassport>((resolve) => {
        resolveCreate = resolve;
      }),
    );
    vi.mocked(api.economics.technicalPassports)
      .mockResolvedValueOnce([passport("P-1", "Блок 4", "SITE_DRESVA")])
      .mockResolvedValueOnce([passport("P-9", "Блок Дайки", "SITE_DAYKA")]);
    const props = { variants: [{ key: "left", label: "Вариант 1", geometry: GEOMETRY }] };
    const { rerender } = render(
      <PassportBar {...props} objectName={DRESVA} onOpenEconomics={vi.fn()} />,
    );
    await findPassport("Блок 4");
    await userEvent.click(screen.getByRole("button", { name: "Сохранить паспорт" }));
    rerender(<PassportBar {...props} objectName={DAYKA} onOpenEconomics={vi.fn()} />);
    await findPassport("Блок Дайки");
    resolveCreate(passport("P-2", "Паспорт Дресьвы", "SITE_DRESVA"));
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Сохранить паспорт" }).hasAttribute("disabled")).toBe(
        false,
      ),
    );
    expect(queryPassport("Паспорт Дресьвы")).toBeNull();
  });

  it("ошибка удаления показывается, а строка остаётся", async () => {
    vi.mocked(api.economics.deleteTechnicalPassport).mockRejectedValue(
      new Error("Технический паспорт P-1 удалён."),
    );
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(true);
    setup();
    await findPassport("Блок 4");
    await userEvent.click(screen.getByRole("button", { name: "Удалить" }));
    await screen.findByText("Технический паспорт P-1 удалён.");
    expect(queryPassport("Блок 4")).not.toBeNull();
    confirm.mockRestore();
  });
});
