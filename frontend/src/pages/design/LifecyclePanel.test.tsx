// @vitest-environment jsdom
// Статус меняется у сохранённой версии паспорта: пока есть несохранённые
// правки, переход недоступен, и панель говорит почему.
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { LifecyclePanel } from "./LifecyclePanel";

function panel(unsaved: boolean) {
  return render(
    <LifecyclePanel
      designId="d-1"
      status="draft"
      revision={2}
      parentDesignId=""
      designedSha256=""
      events={[]}
      busy={false}
      unsaved={unsaved}
      confirm
      note=""
      onConfirmChange={vi.fn()}
      onNoteChange={vi.fn()}
      onTransition={vi.fn()}
      onFork={vi.fn()}
    />,
  );
}

afterEach(cleanup);

describe("LifecyclePanel: несохранённые правки", () => {
  it("переход недоступен, панель просит сохранить", () => {
    panel(true);

    expect(screen.getByRole("button", { name: "На проверку" })).toHaveProperty("disabled", true);
    expect(screen.getByText(/сначала сохраните паспорт/i)).toBeTruthy();
  });

  it("без несохранённых правок переход доступен и подсказки нет", () => {
    panel(false);

    expect(screen.getByRole("button", { name: "На проверку" })).toHaveProperty("disabled", false);
    expect(screen.queryByText(/сначала сохраните паспорт/i)).toBeNull();
  });
});
