// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { FrozenBanner } from "./FrozenBanner";

afterEach(cleanup);

describe("FrozenBanner", () => {
  it("утверждённый паспорт: «Создать ревизию» создаёт копию", async () => {
    const onFork = vi.fn();
    render(<FrozenBanner status="approved" saved unsaved={false} busy={false} onFork={onFork} />);
    expect(screen.getByRole("status").textContent).toContain("Паспорт утверждён: проект не правится");
    await userEvent.click(screen.getByRole("button", { name: "Создать ревизию" }));
    expect(onFork).toHaveBeenCalled();
  });

  it("закрытый паспорт с несохранёнными правками: кнопка недоступна и сказано почему", () => {
    render(<FrozenBanner status="closed" saved unsaved busy={false} onFork={vi.fn()} />);
    expect(screen.getByRole("status").textContent).toContain("Паспорт закрыт");
    expect(screen.getByRole("button", { name: "Создать ревизию" })).toBeDisabled();
    expect(screen.getByText(/Сначала сохраните правки/)).toBeTruthy();
  });

  it("несохранённый паспорт: кнопки нет", () => {
    render(<FrozenBanner status="in_review" saved={false} unsaved={false} busy={false} onFork={vi.fn()} />);
    expect(screen.queryByRole("button")).toBeNull();
  });
});
