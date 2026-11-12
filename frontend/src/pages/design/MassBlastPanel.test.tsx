// @vitest-environment jsdom
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";

const features = { intelligence: false, drill_passport: true, mass_blast_v2: true };
vi.mock("../../app/useFeatures", () => ({ useFeatures: () => features }));
vi.mock("./massBlast/LegacyPanel", () => ({ LegacyMassBlastPanel: () => <div>Прежняя панель</div> }));
vi.mock("./massBlast/MassBlastDialog", () => ({ MassBlastDialog: () => <div>Окно проекта</div> }));
vi.mock("../../api/endpoints", () => ({
  api: {
    design: { listPlans: vi.fn() },
    massBlast: {
      list: vi.fn(),
      getV2: vi.fn(),
      saveV2: vi.fn(),
      newProject: vi.fn(),
      packageUrl: (id: string) => `/package/${id}`,
    },
  },
}));

import { api } from "../../api/endpoints";
import { MassBlastPanel } from "./MassBlastPanel";
import { installDialog, projectV2 } from "./massBlast/testFixtures";

beforeAll(installDialog);
afterEach(cleanup);

beforeEach(() => {
  features.mass_blast_v2 = true;
  vi.mocked(api.massBlast.list).mockReset().mockResolvedValue([]);
  vi.mocked(api.massBlast.getV2).mockReset();
  vi.mocked(api.design.listPlans).mockReset().mockResolvedValue({ items: [
    { design_id: "d66", name: "Блок 66", updated_at: "", hole_count: 196 },
    { design_id: "d67", name: "Блок 67", updated_at: "", hole_count: 150 },
  ] } as never);
  vi.mocked(api.massBlast.newProject).mockReset().mockResolvedValue(projectV2());
});

const summary = { id: "p1", block_design_ids: ["d66"] } as never;

describe("панель «Проект МВ»", () => {
  it("модуль выключен — прежняя панель", () => {
    features.mass_blast_v2 = false;
    render(<MassBlastPanel designId="d66" designName="Блок 66" />);
    expect(screen.getByText("Прежняя панель")).toBeTruthy();
    expect(api.massBlast.list).not.toHaveBeenCalled();
  });

  it("новый проект: дата взрыва обязательна, блоки — галочками", async () => {
    const user = userEvent.setup();
    render(<MassBlastPanel designId="d66" designName="Блок 66" />);
    await user.click(await screen.findByRole("button", { name: "Создать проект МВ" }));
    await user.click(await screen.findByLabelText("Блок 67"));
    await user.click(screen.getByRole("button", { name: "Создать проект" }));
    expect(api.massBlast.newProject).not.toHaveBeenCalled();
    await user.type(screen.getByLabelText("Дата взрыва"), "2026-11-20");
    await user.click(screen.getByRole("button", { name: "Создать проект" }));
    await waitFor(() => expect(api.massBlast.newProject).toHaveBeenCalledWith({
      design_ids: ["d66", "d67"], blast_date: "2026-11-20", blast_time: "",
    }));
    expect(await screen.findByText("Окно проекта")).toBeTruthy();
  });

  it("черновик по прежней форме можно перевести на ВМ.09.03", async () => {
    const user = userEvent.setup();
    vi.spyOn(window, "confirm").mockReturnValue(true);
    vi.mocked(api.massBlast.list).mockResolvedValue([summary]);
    vi.mocked(api.massBlast.getV2).mockResolvedValue(projectV2({ context_version: 1 }));
    vi.mocked(api.massBlast.saveV2).mockResolvedValue(projectV2());
    render(<MassBlastPanel designId="d66" designName="Блок 66" />);
    expect(await screen.findByText("Прежняя панель")).toBeTruthy();
    await user.click(screen.getByRole("button", { name: "Перевести на форму ВМ.09.03" }));
    await waitFor(() => expect(api.massBlast.saveV2).toHaveBeenCalled());
    const [, input] = vi.mocked(api.massBlast.saveV2).mock.calls[0];
    expect(input.context_version).toBe(2);
    expect(input.expected_version).toBe(3);
  });

  it("утверждённый проект: «Весь комплект» на панели", async () => {
    vi.mocked(api.massBlast.list).mockResolvedValue([summary]);
    vi.mocked(api.massBlast.getV2).mockResolvedValue(projectV2({ lifecycle_status: "approved", current_revision_id: "r1" }));
    render(<MassBlastPanel designId="d66" designName="Блок 66" />);
    expect(await screen.findByRole("button", { name: "Весь комплект" })).toBeTruthy();
    expect(screen.getByText(/утверждён · ревизия выпущена/)).toBeTruthy();
  });
});
