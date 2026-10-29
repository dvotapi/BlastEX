// @vitest-environment jsdom
import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it } from "vitest";
import { PayrollBreakdown } from "./PayrollBreakdown";
import { PayrollChart } from "./PayrollChart";
import { money } from "./format";
import { payrollFixture } from "./testFixtures";

afterEach(cleanup);

const FLAG = "Доля экипажа в марже на потолке шкалы выше порога — проверьте цену метра.";

describe("PayrollBreakdown", () => {
  it("закрыт по умолчанию и открывается по клику на summary", async () => {
    const { container } = render(<PayrollBreakdown payroll={payrollFixture()} />);
    const details = container.querySelector("details") as HTMLDetailsElement;
    expect(details.open).toBe(false);
    expect(within(details).getByText("ФОТ по методике")).toBeTruthy();
    await userEvent.click(container.querySelector("summary") as HTMLElement);
    expect(details.open).toBe(true);
  });

  it("summary: цена метра и доля на потолке выше порога — warn, без текста флага", () => {
    const payroll = payrollFixture();
    payroll.margin.ceiling!.crew_share = 1.043;
    payroll.margin.flags = [{ code: "CREW_SHARE_OVER", message: FLAG }];
    const { container } = render(<PayrollBreakdown payroll={payroll} />);
    const summary = container.querySelector("summary") as HTMLElement;
    expect(summary.textContent).toContain(`${money(800)} ₽/м`);
    const share = summary.querySelector(".payroll-share") as HTMLElement;
    expect(share.textContent).toBe("доля на потолке 104,3 % при пороге 30 %");
    expect(share.className).toContain("payroll-share-warn");
    expect(container.textContent).not.toContain(payroll.margin.flags[0].message);
  });

  it("ниже порога — без warn", () => {
    const payroll = payrollFixture();
    payroll.margin.ceiling!.crew_share = 0.25;
    const { container } = render(<PayrollBreakdown payroll={payroll} />);
    const share = container.querySelector("summary .payroll-share") as HTMLElement;
    expect(share.className).not.toContain("payroll-share-warn");
    expect(share.textContent).toBe("доля на потолке 25 % при пороге 30 %");
  });

  it("ступени без потолка: доля при плановом темпе, график без нормы и потолка, но с темпом", () => {
    const { container } = render(<PayrollBreakdown payroll={payrollFixture({ scale: "STEP" })} />);
    const share = container.querySelector("summary .payroll-share") as HTMLElement;
    expect(share.textContent).toBe("доля при плановом темпе 42 % при пороге 30 %");
    expect(share.className).toContain("payroll-share-warn");
    const chart = screen.getByRole("img", { name: "График шкалы сдельной премии" });
    expect(chart.querySelector(".payroll-chart-marker-norm")).toBeNull();
    expect(chart.querySelector(".payroll-chart-marker-ceiling")).toBeNull();
    expect(chart.querySelector(".payroll-chart-marker-pace")).not.toBeNull();
  });

  it("график внутри details, с тремя маркерами и подписью должности", () => {
    const { container } = render(<PayrollBreakdown payroll={payrollFixture()} />);
    const details = container.querySelector("details") as HTMLElement;
    const chart = screen.getByRole("img", { name: "График шкалы сдельной премии" });
    expect(details.contains(chart)).toBe(true);
    for (const kind of ["norm", "ceiling", "pace"]) {
      expect(chart.querySelector(`.payroll-chart-marker-${kind}`)).not.toBeNull();
    }
    expect(details.querySelector(".payroll-chart-title")?.textContent).toContain("Машинист бурового станка");
    expect(details.textContent).toContain("в относительном масштабе");
  });

  it("таблица должностей: строка на каждую с названием и суммами", () => {
    const payroll = payrollFixture();
    const { container } = render(<PayrollBreakdown payroll={payroll} />);
    const rows = container.querySelectorAll(".payroll-table tbody tr");
    expect(rows).toHaveLength(payroll.positions.length);
    payroll.positions.forEach((position, i) => {
      const text = rows[i].textContent ?? "";
      expect(text).toContain(position.position_name);
      expect(text).not.toContain(position.position_code);
      expect(text).toContain(money(position.fixed_rub, 0));
      expect(text).toContain(money(position.variable_rub, 0));
      expect(text).toContain(money(position.amount_rub, 0));
    });
  });

  it("без названия должности показывает нейтральное слово, а не код", () => {
    const payroll = payrollFixture();
    payroll.positions[0].position_name = "";
    const { container } = render(<PayrollBreakdown payroll={payroll} />);
    expect(container.querySelector(".payroll-table tbody tr")?.textContent).toContain("должность");
    expect(container.textContent).not.toContain(payroll.positions[0].position_code);
  });

  it("заголовок графика без названия основной должности не показывает код", () => {
    const payroll = payrollFixture();
    for (const position of payroll.positions) position.position_name = "";
    const { container } = render(<PayrollBreakdown payroll={payroll} />);
    const title = container.querySelector(".payroll-chart-title");
    expect(title).not.toBeNull();
    expect(title!.textContent).toContain("должность");
    expect(title!.textContent).not.toContain(String(payroll.main_position_code));
  });

  it("темп, приведённые метры, смены, цена метра с подписью и две доли", () => {
    const payroll = payrollFixture();
    payroll.margin.lineage = { price_rub_per_m: "формула цены по себестоимости с надбавками" };
    const { container } = render(<PayrollBreakdown payroll={payroll} />);
    const text = container.textContent ?? "";
    expect(text).toContain("120");
    expect(text).toContain("1 500".replace(" ", " "));
    expect(text).toContain("12,5");
    expect(text).toContain("по себестоимости с надбавками");
    expect(text).toContain(`${money(300)} ₽/м`);
    expect(text).toContain("30 %");
    expect(text).toContain("получает машинист бурового станка");
  });

  it("NO_MARGIN: вместо долей пояснение, графика нет при пустом ряде", () => {
    const payroll = payrollFixture();
    payroll.margin = { ...payroll.margin, status: "NO_MARGIN", plan: null, ceiling: null, margin_rub_per_m: null };
    payroll.series = [];
    const { container } = render(<PayrollBreakdown payroll={payroll} />);
    expect(container.querySelector("summary .payroll-share")?.textContent).toBe("доля не проверена: нет маржи метра");
    expect(container.querySelector(".payroll-share-warn")).toBeNull();
    expect(screen.queryByRole("img", { name: "График шкалы сдельной премии" })).toBeNull();
    expect(container.querySelector(".payroll-shares")).toBeNull();
  });
});

describe("PayrollBreakdown: названия и подписи", () => {
  it("строка матрицы показывает название, но не код", () => {
    const { container } = render(<PayrollBreakdown payroll={payrollFixture()} />);
    expect(container.textContent).toContain("Строка матрицы");
    expect(container.textContent).toContain("Гранит, коронка 160");
    expect(container.textContent).not.toContain("COND_GRANITE");
  });

  it("без названия строка матрицы не показывается, код не выводится", () => {
    const payroll = payrollFixture();
    delete payroll.pace.condition_name;
    const { container } = render(<PayrollBreakdown payroll={payroll} />);
    expect(container.textContent).not.toContain("Строка матрицы");
    expect(container.textContent).not.toContain("COND_GRANITE");
  });

  it("заголовок ставки и нейтральная подпись без главной должности", () => {
    const payroll = payrollFixture();
    payroll.main_position_code = null;
    const { container } = render(<PayrollBreakdown payroll={payroll} />);
    expect(container.querySelector(".payroll-table th:nth-child(3)")?.textContent).toBe("Ставка, ₽ за пр. м на человека");
    expect(container.textContent).toContain("получает главный по шкале");
    expect(container.querySelector(".payroll-table-wrap .payroll-table")).not.toBeNull();
  });

  it("svg несёт title и desc с темпом, нормой и потолком", () => {
    render(<PayrollBreakdown payroll={payrollFixture()} />);
    const chart = screen.getByRole("img", { name: "График шкалы сдельной премии" });
    expect(chart.querySelector("title")?.textContent).toBe("График шкалы сдельной премии");
    const desc = chart.querySelector("desc")?.textContent ?? "";
    expect(desc).toContain("плановый темп 120");
    expect(desc).toContain("норма 115,38");
    expect(desc).toContain("потолок 184,62");
  });

  it("близкие маркеры (темп 120 и норма 115) подписаны на разной высоте", () => {
    render(<PayrollBreakdown payroll={payrollFixture()} />);
    const chart = screen.getByRole("img", { name: "График шкалы сдельной премии" });
    const ys = ["norm", "pace"].map((kind) => chart.querySelector(`.payroll-chart-marker-${kind} text`)?.getAttribute("y"));
    expect(ys[0]).not.toBe(ys[1]);
  });
});

describe("PayrollChart", () => {
  it("null без ряда", () => {
    const payroll = payrollFixture();
    payroll.series = [];
    const { container } = render(<PayrollChart payroll={payroll} />);
    expect(container.firstChild).toBeNull();
  });
});
