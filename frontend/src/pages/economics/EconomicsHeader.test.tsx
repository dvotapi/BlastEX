// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ComponentProps } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { EconomicsHeader } from "./EconomicsHeader";
import { draftFromDefaults } from "./scenario";
import { paramsFixture } from "./testFixtures";
import type { EconomicsRunSummary } from "../../types/blockEconomics";

afterEach(cleanup);

const CONTEXT = { site: "Карьер №1", passport: "Блок №12 вер. 1", revision: "Ревизия 3 от 01.01.2026" };

const RUN: EconomicsRunSummary = {
  id: "RUN-1",
  name: "Базовый",
  technical_passport_id: "PASSPORT-1",
  package_code: "DRILL_AND_BLAST",
  reference_revision_id: "REV-1",
  created_at: "2026-01-01T00:00:00Z",
  created_by: "tester@blastex.local",
  price_per_m3: { full: 1500 },
};

function setup(overrides: Partial<ComponentProps<typeof EconomicsHeader>> = {}) {
  const draft = draftFromDefaults("Новый сценарий", paramsFixture());
  const onSave = vi.fn();
  const onDuplicate = vi.fn();
  const onSelectDraft = vi.fn();
  const onOpenRun = vi.fn();
  const onRename = vi.fn();
  const onRemove = vi.fn();
  const props: ComponentProps<typeof EconomicsHeader> = {
    context: CONTEXT,
    drafts: [draft],
    runs: [RUN],
    activeId: draft.id,
    onSelectDraft,
    onOpenRun,
    dirty: true,
    onSave,
    onDuplicate,
    onRename,
    onRemove,
    canRemove: true,
    exportUrl: null,
    busy: false,
    status: "",
    error: "",
    ...overrides,
  };
  render(<EconomicsHeader {...props} />);
  return { onSave, onDuplicate, onSelectDraft, onOpenRun, onRename, onRemove, draft };
}

describe("EconomicsHeader", () => {
  it("заголовок и контекст паспорта на месте", () => {
    setup();

    expect(screen.getByRole("heading", { name: "Экономика блока" })).toBeInTheDocument();
    expect(
      screen.getByText(`${CONTEXT.site} · ${CONTEXT.passport} · ${CONTEXT.revision}`),
    ).toBeInTheDocument();
  });

  it("черновик показывает «Черновик · не сохранено»", () => {
    setup({ dirty: true });

    expect(screen.getByText("Черновик · не сохранено")).toBeInTheDocument();
  });

  it("сохранённый сценарий показывает status вместо метки черновика", () => {
    setup({ dirty: false, status: "Сохранён как «Базовый»" });

    expect(screen.getByText("Сохранён как «Базовый»")).toBeInTheDocument();
    expect(screen.queryByText("Черновик · не сохранено")).not.toBeInTheDocument();
  });

  it("клик «Сохранить», ввод имени и Enter вызывает onSave с именем", async () => {
    const user = userEvent.setup();
    const { onSave } = setup();

    await user.click(screen.getByRole("button", { name: "Сохранить" }));
    await user.type(screen.getByRole("textbox", { name: "Имя сценария" }), "Базовый{Enter}");

    expect(onSave).toHaveBeenCalledWith("Базовый");
  });

  it("Escape в поле имени закрывает его без сохранения", async () => {
    const user = userEvent.setup();
    const { onSave } = setup();

    await user.click(screen.getByRole("button", { name: "Сохранить" }));
    await user.type(screen.getByRole("textbox", { name: "Имя сценария" }), "Черновой{Escape}");

    expect(onSave).not.toHaveBeenCalled();
    expect(screen.queryByRole("textbox", { name: "Имя сценария" })).not.toBeInTheDocument();
  });

  it("кнопка XLSX задизейблена, пока сценарий не сохранён", () => {
    setup({ exportUrl: null });

    expect(screen.getByRole("button", { name: "XLSX" })).toBeDisabled();
    expect(screen.queryByRole("link", { name: "XLSX" })).not.toBeInTheDocument();
  });

  it("сохранённый сценарий даёт ссылку на выгрузку", () => {
    setup({ exportUrl: "/x/RUN-1" });

    expect(screen.getByRole("link", { name: "XLSX" })).toHaveAttribute("href", "/x/RUN-1");
  });

  it("выбор сохранённого прогона в селекторе зовёт onOpenRun, а не onSelectDraft", async () => {
    const user = userEvent.setup();
    const { onOpenRun, onSelectDraft } = setup();

    await user.selectOptions(screen.getByRole("combobox", { name: "Сценарий" }), "RUN-1");

    expect(onOpenRun).toHaveBeenCalledWith("RUN-1");
    expect(onSelectDraft).not.toHaveBeenCalled();
  });

  it("выбор открытого черновика зовёт onSelectDraft", async () => {
    const user = userEvent.setup();
    const firstDraft = draftFromDefaults("Первый вариант", paramsFixture());
    const secondDraft = draftFromDefaults("Второй вариант", paramsFixture());
    const onSelectDraft = vi.fn();
    setup({ drafts: [firstDraft, secondDraft], activeId: firstDraft.id, onSelectDraft });

    await user.selectOptions(screen.getByRole("combobox", { name: "Сценарий" }), secondDraft.id);

    expect(onSelectDraft).toHaveBeenCalledWith(secondDraft.id);
  });

  it("«Дублировать» вызывает onDuplicate", async () => {
    const user = userEvent.setup();
    const { onDuplicate } = setup();

    await user.click(screen.getByRole("button", { name: "Дублировать" }));

    expect(onDuplicate).toHaveBeenCalledTimes(1);
  });

  it("ошибка пересчёта показывается баннером role=alert", () => {
    setup({ error: "Сервис недоступен" });

    expect(screen.getByRole("alert")).toHaveTextContent("Сервис недоступен");
  });

  it("busy отключает выбор сценария и кнопки действий", () => {
    setup({ busy: true });

    expect(screen.getByRole("combobox", { name: "Сценарий" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Сохранить" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Дублировать" })).toBeDisabled();
  });
});
