// @vitest-environment jsdom
// Панель «Подбор раскладки» (часть 4в): запуск, ход по этапам, карточки
// вариантов, предпросмотр и «Применить».
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { emptyNetwork, type LayoutSearchResult, type LayoutSearchStatus, type LayoutSearchVariant } from "../../types/design";
import { LayoutSearchPanel } from "./LayoutSearchPanel";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

function variant(extra: Partial<LayoutSearchVariant> = {}): LayoutSearchVariant {
  return {
    params: { row_azimuth_deg: 30, spacing_a_m: 4.41, burden_b_m: 3.53 },
    cut_flank: "left",
    holes: [],
    network: emptyNetwork(),
    rejected: false,
    reject_codes: [],
    lsp_out: 2,
    fast_share: 0.031,
    converging_length_m: 12.5,
    outside_share: 0.184,
    robust_spread: 0.27,
    hole_count: 64,
    window8_max_holes: 3,
    downhole_ms: 500,
    warnings: [],
    ...extra,
  };
}

function result(extra: Partial<LayoutSearchResult> = {}): LayoutSearchResult {
  return {
    best: [
      variant(),
      variant({ cut_flank: "right", params: { row_azimuth_deg: 35, spacing_a_m: 4.6, burden_b_m: 3.7, front_rows_mode: "pair", front_rows_tilt_deg: 15 } }),
      variant({
        params: { row_azimuth_deg: 40, spacing_a_m: 4.2, burden_b_m: 3.4, front_rows_mode: "taper", front_rows_tilt_count: 2, front_rows_tilt_deg: 12 },
      }),
    ],
    evaluated: 120,
    rejected: 10,
    stopped_early: false,
    elapsed_s: 140,
    all_rejected: false,
    warnings: [],
    ...extra,
  };
}

function status(extra: Partial<LayoutSearchStatus> = {}): LayoutSearchStatus {
  return { state: "done", stage: null, done: 0, total: 0, elapsed_s: 140, fingerprint: "f", result: result(), error: null, ...extra };
}

type Props = Parameters<typeof LayoutSearchPanel>[0];

function mount(extra: Partial<Props> = {}) {
  const props: Props = {
    designId: "d1",
    status: status(),
    stale: false,
    error: null,
    manualCount: 0,
    locked: false,
    previewIndex: null,
    onStart: vi.fn(),
    onStop: vi.fn(),
    onPreview: vi.fn(),
    onApply: vi.fn(),
    ...extra,
  };
  const view = render(<LayoutSearchPanel {...props} />);
  return { props, view };
}

const START = "Подобрать раскладку";

/** Кнопки показа «Вариант N» — заголовки карточек. */
function cards(): HTMLElement[] {
  return screen.getAllByRole("button", { name: /^Вариант \d/ });
}

function card(index: number): HTMLElement {
  return cards()[index].closest(".layout-variant-card") as HTMLElement;
}

describe("LayoutSearchPanel: запуск", () => {
  it("без design_id кнопка неактивна, с подсказкой", () => {
    mount({ designId: null, status: null });
    expect((screen.getByRole("button", { name: START }) as HTMLButtonElement).disabled).toBe(true);
    expect(screen.getByText("Сохраните паспорт, чтобы подобрать раскладку")).toBeTruthy();
  });

  it("при закрытом паспорте кнопка неактивна", () => {
    mount({ locked: true, status: null });
    expect((screen.getByRole("button", { name: START }) as HTMLButtonElement).disabled).toBe(true);
  });

  it("кнопка запускает подбор", () => {
    const { props } = mount({ status: null });
    fireEvent.click(screen.getByRole("button", { name: START }));
    expect(props.onStart).toHaveBeenCalledTimes(1);
  });

  it("ошибка запуска видна", () => {
    mount({ status: null, error: "Подбор раскладки уже идёт: блок «№65». Дождитесь окончания или остановите его." });
    expect(screen.getByRole("alert").textContent).toContain("уже идёт");
  });
});

describe("LayoutSearchPanel: ход подбора", () => {
  it.each([
    ["geometry", "Геометрия сетки: 12 из 40"],
    ["front_rows", "Первый ряд у откоса: 3 из 9"],
    ["refine", "Уточнение: 5 из 20"],
  ] as const)("этап %s подписан по-русски", (stage, text) => {
    const [done, total] = text.match(/(\d+) из (\d+)/)!.slice(1).map(Number);
    mount({ status: status({ state: "running", stage, done, total, elapsed_s: 37, result: null }) });
    expect(screen.getByText(text)).toBeTruthy();
    expect(screen.getByText(/37 с/)).toBeTruthy();
  });

  it("статус «идёт» подписан и во время подбора", () => {
    mount({ status: status({ state: "running", stage: "refine", done: 1, total: 2, result: null }) });
    expect(screen.getByText("Подбор: идёт")).toBeTruthy();
  });

  it("карточка не вкладывает кнопки в кнопку", () => {
    mount();
    expect(card(0).getAttribute("role")).toBeNull();
    expect(cards()[0].tagName).toBe("BUTTON");
  });

  it("«Остановить» вызывает остановку, запуск неактивен", () => {
    const { props } = mount({ status: status({ state: "running", stage: "geometry", done: 1, total: 10, result: null }) });
    fireEvent.click(screen.getByRole("button", { name: "Остановить" }));
    expect(props.onStop).toHaveBeenCalledTimes(1);
    expect((screen.getByRole("button", { name: START }) as HTMLButtonElement).disabled).toBe(true);
  });

  it("ошибка подбора показывается текстом сервера", () => {
    const text = "Подбор раскладки завершился с ошибкой. Подробности — в журнале сервера.";
    mount({ status: status({ state: "failed", result: null, error: text }) });
    expect(screen.getByText(text)).toBeTruthy();
  });

  it("сразу после запуска (всего 0) — «Подготовка…», а не «0 из 0»", () => {
    mount({ status: status({ state: "running", stage: null, done: 0, total: 0, elapsed_s: 0, result: null }) });
    expect(screen.getByText("Подготовка…")).toBeTruthy();
    expect(screen.queryByText(/0 из 0/)).toBeNull();
  });
});

describe("LayoutSearchPanel: карточки", () => {
  it("три карточки с параметрами и подписями показателей", () => {
    mount();
    expect(cards()).toHaveLength(3);
    const first = within(card(0));
    for (const label of [
      "Азимут рядов, °",
      "Шаги a × b, м",
      "Первый ряд",
      "Вруб у фланга",
      "ЛСП вне коридора",
      "Быстрее 3 мс/м, %",
      "Стыки фронтов, м",
      "Вне коридора ±25 %, %",
      "Разброс темпа",
      "Скважин",
      "В окне 8 мс (справочно)",
      "Замедление в скважине, мс",
    ]) {
      expect(first.getByText(label)).toBeTruthy();
    }
    expect(first.getByText("4,41 × 3,53")).toBeTruthy();
    expect(first.getByText("вертикальный")).toBeTruthy();
    expect(first.getByText("левого")).toBeTruthy();
    expect(first.getByText("18")).toBeTruthy(); // 0,184 → 18 %
    expect(first.getByText("64")).toBeTruthy();
    expect(within(card(1)).getByText("пара 15°")).toBeTruthy();
    expect(within(card(1)).getByText("правого")).toBeTruthy();
    expect(within(card(2)).getByText("переход, 2 ряда, 12°")).toBeTruthy();
  });

  it("показатель без значения — прочерк, без служебных имён", () => {
    mount({ status: status({ result: result({ best: [variant({ fast_share: null, robust_spread: null })] }) }) });
    expect(within(card(0)).getAllByText("—").length).toBe(2);
    expect(screen.queryByText(/fast_share|row_azimuth/)).toBeNull();
  });

  it("отбракованная карточка — с причинами человеческим языком", () => {
    mount({
      status: status({
        result: result({
          best: [variant({ rejected: true, reject_codes: ["floor_beyond_toe", "collar_too_close_to_crest", "something_new"] })],
        }),
      }),
    });
    const scope = within(card(0));
    expect(scope.getByText("не прошёл проверки")).toBeTruthy();
    expect(scope.getByText(/забой за подошвой откоса/)).toBeTruthy();
    expect(scope.getByText(/устье ближе допустимого к кромке/)).toBeTruthy();
    expect(scope.getByText(/не прошёл проверку/)).toBeTruthy();
    expect(screen.queryByText(/floor_beyond_toe/)).toBeNull();
  });

  it("пустая сетка — «сетка не построилась»", () => {
    mount({ status: status({ result: result({ best: [variant({ rejected: true, reject_codes: ["empty"] })] }) }) });
    expect(within(card(0)).getByText(/сетка не построилась/)).toBeTruthy();
  });
});

describe("LayoutSearchPanel: пометки результата", () => {
  it("all_rejected", () => {
    mount({ status: status({ result: result({ all_rejected: true }) }) });
    expect(screen.getByText("Ни один вариант не прошёл проверки — показаны лучшие из отбракованных.")).toBeTruthy();
  });

  it("остановка пользователем — одна пометка", () => {
    const { view } = mount({ status: status({ state: "stopped", result: result({ stopped_early: true }) }) });
    expect(screen.getByText("Подбор остановлен — показано лучшее найденное.")).toBeTruthy();
    expect(view.container.textContent!.match(/остановлен/g)).toHaveLength(1);
    expect(screen.queryByText(/Время подбора вышло/)).toBeNull();
  });

  it("конец бюджета (done, stopped_early) — «время вышло», не «остановлен»", () => {
    const { view } = mount({ status: status({ state: "done", result: result({ stopped_early: true }) }) });
    expect(screen.getByText("Время подбора вышло — показано лучшее найденное.")).toBeTruthy();
    expect(view.container.textContent).not.toMatch(/остановлен/);
    expect(view.container.textContent!.match(/показано лучшее найденное/g)).toHaveLength(1);
  });

  it("остановлен до первой оценки — только предупреждение сервера", () => {
    const nothing = "Подбор остановлен до первой оценки.";
    const { view } = mount({
      status: status({ state: "stopped", result: result({ best: [], stopped_early: true, warnings: [nothing] }) }),
    });
    expect(screen.getByText(nothing)).toBeTruthy();
    expect(view.container.textContent).not.toMatch(/показано лучшее найденное/);
  });

  it("все отбракованы — одна пометка", () => {
    const { view } = mount({ status: status({ result: result({ all_rejected: true }) }) });
    expect(view.container.textContent!.match(/отбракованных/g)).toHaveLength(1);
  });

  it("«Устарел»", () => {
    mount({ stale: true });
    expect(screen.getByText("Устарел: контур, съёмка или параметры изменились после подбора")).toBeTruthy();
  });

  it("предупреждения результата — списком", () => {
    mount({ status: status({ result: result({ warnings: ["Порода «Гранит» не найдена в справочнике."] }) }) });
    expect(screen.getByText("Порода «Гранит» не найдена в справочнике.")).toBeTruthy();
  });

  it("без пометок, когда всё в порядке", () => {
    mount();
    expect(screen.queryByText(/Устарел/)).toBeNull();
    expect(screen.queryByText(/Ни один вариант/)).toBeNull();
    expect(screen.queryByText(/Подбор остановлен/)).toBeNull();
  });
});

describe("LayoutSearchPanel: предпросмотр и «Применить»", () => {
  it("клик по карточке — показ, повторный — снятие", () => {
    const { props, view } = mount();
    fireEvent.click(cards()[0]);
    expect(props.onPreview).toHaveBeenLastCalledWith(0);
    view.rerender(<LayoutSearchPanel {...props} previewIndex={0} />);
    expect(cards()[0].getAttribute("aria-pressed")).toBe("true");
    fireEvent.click(cards()[0]);
    expect(props.onPreview).toHaveBeenLastCalledWith(null);
  });

  it("«Скрыть» убирает показ", () => {
    const { props } = mount({ previewIndex: 1 });
    fireEvent.click(within(card(1)).getByRole("button", { name: "Скрыть" }));
    expect(props.onPreview).toHaveBeenLastCalledWith(null);
  });

  it("«Применить» на варианте 2 при показе варианта 1 применяет вариант 2", () => {
    const { props } = mount({ previewIndex: 0 });
    fireEvent.click(within(card(1)).getByRole("button", { name: "Применить" }));
    expect(props.onApply).toHaveBeenCalledTimes(1);
    expect(props.onApply).toHaveBeenCalledWith(props.status!.result!.best[1]);
    // Кнопка внутри карточки не переключает показ.
    expect(props.onPreview).not.toHaveBeenCalled();
  });

  it("ручные скважины — сначала подтверждение; отказ ничего не меняет", () => {
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(false);
    const { props } = mount({ manualCount: 3 });
    fireEvent.click(within(card(0)).getByRole("button", { name: "Применить" }));
    expect(confirm).toHaveBeenCalledWith("Ручные правки (3) будут потеряны. Применить вариант?");
    expect(props.onApply).not.toHaveBeenCalled();

    confirm.mockReturnValue(true);
    fireEvent.click(within(card(0)).getByRole("button", { name: "Применить" }));
    expect(props.onApply).toHaveBeenCalledWith(props.status!.result!.best[0]);
  });

  it("без ручных скважин и свежий результат — без подтверждения", () => {
    const confirm = vi.spyOn(window, "confirm");
    const { props } = mount();
    fireEvent.click(within(card(0)).getByRole("button", { name: "Применить" }));
    expect(confirm).not.toHaveBeenCalled();
    expect(props.onApply).toHaveBeenCalledTimes(1);
  });

  it("устаревший результат — подтверждение перед применением", () => {
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(false);
    const { props } = mount({ stale: true });
    fireEvent.click(within(card(0)).getByRole("button", { name: "Применить" }));
    expect(confirm).toHaveBeenCalledTimes(1);
    expect(confirm.mock.calls[0][0]).toMatch(/Устарел/);
    expect(props.onApply).not.toHaveBeenCalled();
  });

  it("закрытый паспорт — «Применить» неактивно, показ доступен", () => {
    const { props } = mount({ locked: true });
    expect((within(card(0)).getByRole("button", { name: "Применить" }) as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(cards()[0]);
    expect(props.onPreview).toHaveBeenCalledWith(0);
  });
});

describe("LayoutSearchPanel: границы темпа итога", () => {
  it("подпись доли быстрых — по нижней границе запуска", () => {
    mount({ status: status({ result: result({ relief_min_ms_m: 4.5, relief_max_ms_m: 12 }) }) });
    expect(within(card(0)).getByText("Быстрее 4,5 мс/м, %")).toBeTruthy();
  });

  it("итог прежней версии без границ — 3 мс/м", () => {
    mount();
    expect(within(card(0)).getByText("Быстрее 3 мс/м, %")).toBeTruthy();
  });

  it("границы породы изменились — своя пометка «Устарел»", () => {
    mount({ stale: true, status: status({ bounds_changed: true }) });
    expect(screen.getByText("Устарел: границы темпа отбойки породы изменились после подбора")).toBeTruthy();
  });
});
