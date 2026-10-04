// @vitest-environment jsdom
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../../api/endpoints", () => ({
  api: {
    massBlast: {
      list: vi.fn(),
      get: vi.fn(),
      accounts: vi.fn(),
      create: vi.fn(),
      documents: vi.fn(),
      attachments: vi.fn(),
    },
  },
}));

import { api } from "../../api/endpoints";
import type { MassBlastProject, MassBlastProjectSummary } from "../../types/design";
import { MassBlastPanel } from "./MassBlastPanel";

afterEach(cleanup);

const ACCOUNTS = [
  { email: "manager@example.ru", display_name: "Иванов И. И." },
  { email: "supervisor@example.ru", display_name: "Петров П. П." },
];

function project(): MassBlastProject {
  return {
    id: "project-1", name: "Массовый взрыв", site_code: "SITE-1", object_name: "Карьер", blast_date: "2026-10-10",
    lifecycle_status: "draft", version: 1, current_revision_id: null, block_design_ids: ["design-1"],
    updated_at: "", customer_code: "", blast_time: "", document_profile_code: "STANDARD", reference_revision_id: null,
    blocks: [{ design_id: "design-1" }],
    responsibilities: [
      { role_code: "blast_manager", employee_code: "Иванов", employee_name: "Иванов", position_name: "Руководитель взрывных работ", account_email: "manager@example.ru" },
      { role_code: "explosives_supervisor", employee_code: "Петров", employee_name: "Петров", position_name: "Ответственный за ВМ", account_email: "supervisor@example.ru" },
    ],
    safety_plan: {}, charging_schedule: [], signal_plan: {}, guard_posts: [], notifications: [],
    created_at: "", created_by: "", updated_by: "",
  } as MassBlastProject;
}

function summary(): MassBlastProjectSummary {
  return { ...project(), block_design_ids: ["design-1"] };
}

beforeEach(() => {
  vi.mocked(api.massBlast.list).mockReset().mockResolvedValue([]);
  vi.mocked(api.massBlast.accounts).mockReset().mockResolvedValue(ACCOUNTS);
  vi.mocked(api.massBlast.create).mockReset().mockResolvedValue(project());
  vi.mocked(api.massBlast.documents).mockReset().mockResolvedValue([]);
  vi.mocked(api.massBlast.attachments).mockReset().mockResolvedValue([]);
});

describe("MassBlastPanel — учётки ответственных", () => {
  it("выбранная учётка уходит в черновике у своей роли", async () => {
    render(<MassBlastPanel designId="design-1" designName="Блок 1" />);
    await screen.findAllByRole("option", { name: "Иванов И. И." });

    await userEvent.type(screen.getByLabelText("Руководитель ВР"), "Иванов");
    await userEvent.selectOptions(screen.getByLabelText("Учётка руководителя ВР"), "manager@example.ru");
    await userEvent.type(screen.getByLabelText("Ответственный за ВМ"), "Петров");
    await userEvent.selectOptions(screen.getByLabelText("Учётка ответственного за ВМ"), "supervisor@example.ru");
    await userEvent.click(screen.getByRole("button", { name: "Сохранить черновик" }));

    await waitFor(() => expect(api.massBlast.create).toHaveBeenCalledTimes(1));
    const sent = vi.mocked(api.massBlast.create).mock.calls[0][0];
    expect(sent.responsibilities.map((item) => [item.role_code, item.account_email])).toEqual([
      ["blast_manager", "manager@example.ru"],
      ["explosives_supervisor", "supervisor@example.ru"],
    ]);
  });

  it("учётка без ФИО не теряется молча: черновик не уходит, есть подсказка", async () => {
    render(<MassBlastPanel designId="design-1" designName="Блок 1" />);
    await screen.findAllByRole("option", { name: "Иванов И. И." });

    await userEvent.selectOptions(screen.getByLabelText("Учётка руководителя ВР"), "manager@example.ru");
    await userEvent.click(screen.getByRole("button", { name: "Сохранить черновик" }));

    expect(await screen.findByText(/Укажите ФИО: Руководитель ВР/)).toBeTruthy();
    expect(api.massBlast.create).not.toHaveBeenCalled();
  });

  it("сохранённый проект показывает назначенные учётки", async () => {
    vi.mocked(api.massBlast.list).mockResolvedValue([summary()]);
    vi.mocked(api.massBlast.get).mockReset().mockResolvedValue(project());
    render(<MassBlastPanel designId="design-1" designName="Блок 1" />);

    await waitFor(() =>
      expect((screen.getByLabelText("Учётка ответственного за ВМ") as HTMLSelectElement).value).toBe("supervisor@example.ru"),
    );
    expect((screen.getByLabelText("Учётка руководителя ВР") as HTMLSelectElement).value).toBe("manager@example.ru");
  });

  it("недействующая учётка не теряется при открытии проекта", async () => {
    vi.mocked(api.massBlast.list).mockResolvedValue([summary()]);
    vi.mocked(api.massBlast.get).mockReset().mockResolvedValue(project());
    vi.mocked(api.massBlast.accounts).mockResolvedValue([ACCOUNTS[0]]);
    render(<MassBlastPanel designId="design-1" designName="Блок 1" />);

    await waitFor(() =>
      expect((screen.getByLabelText("Учётка ответственного за ВМ") as HTMLSelectElement).value).toBe("supervisor@example.ru"),
    );
    expect(screen.getByRole("option", { name: "supervisor@example.ru (нет среди действующих)" })).toBeTruthy();
  });
});
