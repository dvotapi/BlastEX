// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../../../api/endpoints", () => ({
  api: { blockEconomics: { drillingSensitivity: vi.fn(), drillingWhatIf: vi.fn() } },
}));

import { api } from "../../../api/endpoints";
import { DrillingPriceDrivers, premiumBounds } from "./DrillingPriceDrivers";
import { drillingSensitivityFixture, paramsFixture } from "../testFixtures";
import { whatIfRange } from "./WhatIfSlider";
import { scaleChanged } from "./PremiumCurveChart";

beforeEach(() => {
  vi.mocked(api.blockEconomics.drillingSensitivity).mockResolvedValue(drillingSensitivityFixture());
  vi.mocked(api.blockEconomics.drillingWhatIf).mockResolvedValue({
    base: drillingSensitivityFixture().base,
    result: { ...drillingSensitivityFixture().base, without_payroll_rub_per_m: 240, with_payroll_rub_per_m: 320 },
    reference_revision_id: "REV-1",
  });
});

afterEach(() => {
  cleanup();
  vi.resetAllMocks();
});

const params = paramsFixture();
const slider = (name: string) => screen.getByRole("slider", { name }) as HTMLInputElement;

describe("DrillingPriceDrivers", () => {
  it("показывает четыре самых сильных ручки, параметр черновика без бегунка и блок премии", async () => {
    render(<DrillingPriceDrivers passportId="PASSPORT-1" params={params} />);

    expect(await screen.findByText("260,00 ₽/м")).toBeInTheDocument();
    expect(screen.getByText("340,00 ₽/м")).toBeInTheDocument();
    expect(screen.getByText(/в смету и справочники не пишутся/)).toBeInTheDocument();
    expect(api.blockEconomics.drillingSensitivity).toHaveBeenCalledWith("PASSPORT-1", params);

    expect(slider("Техническая скорость станка").value).toBe("12");
    expect(slider("Цена дизельного топлива")).toBeInTheDocument();
    expect(slider("Стойкость ППУ")).toBeInTheDocument();
    // Ручки участка — отдельным списком, все, хотя по силе они слабее пятой.
    const site = screen.getByRole("heading", { name: /Участок бурения/ }).parentElement as HTMLElement;
    expect(within(site).getAllByRole("slider").map((input) => input.getAttribute("aria-label"))).toEqual([
      "Услуги трала",
      "Оклад: Механик",
      "Питание",
    ]);
    // Пятая ручка в четвёрку не вошла.
    expect(screen.queryByRole("slider", { name: "Стойкость коронки" })).toBeNull();
    // Плановые смены — параметр черновика: строка есть, бегунка нет.
    expect(screen.queryByRole("slider", { name: "Плановые смены станка" })).toBeNull();
    expect(screen.getByText(/меняется бегунком «Загрузка станка»/)).toBeInTheDocument();
    // Эффект +10 % — половина размаха между плечами.
    expect(screen.getByText("+10 %: −20,00 ₽/м")).toBeInTheDocument();

    const premium = screen.getByRole("heading", { name: /Премия машинистов/ }).parentElement as HTMLElement;
    expect(within(premium).getByRole("slider", { name: "Норма за смену" })).toBeInTheDocument();
    expect(within(premium).getByRole("slider", { name: "Расценка на потолке" })).toBeInTheDocument();
    expect(within(premium).getByText(/Машинист буровой установки/)).toBeInTheDocument();
    // Запросов «что если» без подмен нет.
    expect(api.blockEconomics.drillingWhatIf).not.toHaveBeenCalled();

    // Кольцо слагаемых: четыре сегмента, в легенде доли и ₽/м; график премии с отметками.
    const donut = screen.getByRole("figure", { name: "Слагаемые стоимости метра" });
    // Четыре слагаемых и две подстатьи ФОТ экипажа: машинист 50 из 340 — 14,71 % цены метра.
    expect(within(donut).getAllByRole("listitem")).toHaveLength(6);
    const driller = within(donut).getByText("Машинист буровой установки").closest("li") as HTMLElement;
    expect(within(driller).getByText("14,71 %")).toBeInTheDocument();
    expect(within(donut).getByText("ФОТ экипажа")).toBeInTheDocument();
    expect(within(donut).getByText("35,29 %")).toBeInTheDocument();
    expect(within(donut).getByText("340")).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "График шкалы премии машиниста" })).toBeInTheDocument();
    // Вторая линия — премия за смену по правой оси.
    expect(screen.getByTestId("premium-curve-shift").getAttribute("d")).toMatch(/^M/);
    expect(screen.getByText("премия за смену, ₽", { selector: "li" })).toBeInTheDocument();
    expect(screen.getByText(/норма 115/)).toBeInTheDocument();
    expect(screen.getByText(/темп 120/)).toBeInTheDocument();
    expect(screen.queryByTestId("premium-curve-base")).toBeNull();
  });

  it("пробная шкала рисуется поверх справочной: кольцо и график берутся из ответа «что если»", async () => {
    const fixture = drillingSensitivityFixture();
    const result = {
      ...fixture.base,
      with_payroll_rub_per_m: 360,
      components: fixture.base.components.map((c) => (c.code === "CREW_PAYROLL" ? { ...c, rub_per_m: 100 } : c)),
      premium_curve: {
        ...fixture.base.premium_curve!,
        scale: { ...fixture.base.premium_curve!.scale, rate_norm: 60 },
        series: fixture.base.premium_curve!.series.map((p) => ({ ...p, rate: Math.max(p.rate, 60) })),
      },
    };
    vi.mocked(api.blockEconomics.drillingWhatIf).mockResolvedValue({ base: fixture.base, result, reference_revision_id: "REV-1" });
    render(<DrillingPriceDrivers passportId="PASSPORT-1" params={params} />);
    await screen.findByText("260,00 ₽/м");

    const rate = slider("Расценка на норме");
    fireEvent.change(rate, { target: { value: "60" } });
    fireEvent.pointerUp(rate);

    await screen.findByText("360,00 ₽/м");
    const donut = screen.getByRole("figure", { name: "Слагаемые стоимости метра" });
    expect(within(donut).getByText("360")).toBeInTheDocument();
    expect(screen.getByTestId("premium-curve-base")).toBeInTheDocument();
    expect(screen.getByText(/норма 115 · 60,0 ₽/)).toBeInTheDocument();
    expect(screen.getByText("справочник")).toBeInTheDocument();
    expect(screen.getByText("пробная шкала, ₽ за прив. м")).toBeInTheDocument();
  });

  it("скорость станка двигает темп машиниста: подпись у ручки и две отметки темпа на графике", async () => {
    const fixture = drillingSensitivityFixture();
    const result = { ...fixture.base, with_payroll_rub_per_m: 330, premium_curve: { ...fixture.base.premium_curve!, pace: 132 } };
    vi.mocked(api.blockEconomics.drillingWhatIf).mockResolvedValue({ base: fixture.base, result, reference_revision_id: "REV-1" });
    render(<DrillingPriceDrivers passportId="PASSPORT-1" params={params} />);
    await screen.findByText("260,00 ₽/м");
    expect(screen.getByText(/темп машиниста 120 прив\. м\/см/)).toBeInTheDocument();
    expect(screen.queryByTestId("premium-curve-pace-base")).toBeNull();

    const speed = slider("Техническая скорость станка");
    fireEvent.change(speed, { target: { value: "13.2" } });
    fireEvent.pointerUp(speed);

    // Ответ «что если» приходит после паузы бегунка: в CI под нагрузкой дольше секунды.
    await screen.findByText("330,00 ₽/м", undefined, { timeout: 5000 });
    expect(screen.getByText(/темп машиниста 120 → 132 прив\. м\/см/)).toBeInTheDocument();
    expect(screen.getByText(/темп 120 → 132 ·/)).toBeInTheDocument();
    expect(screen.getByTestId("premium-curve-pace-base")).toBeInTheDocument();
    // Шкала не менялась — справочной пунктирной кривой нет.
    expect(screen.queryByTestId("premium-curve-base")).toBeNull();
  });

  it("отпускание бегунка шлёт один запрос «что если», цена помечена «считается…», «Вернуть» возвращает базу", async () => {
    type WhatIf = Awaited<ReturnType<typeof api.blockEconomics.drillingWhatIf>>;
    let release: (value: WhatIf) => void = () => {};
    vi.mocked(api.blockEconomics.drillingWhatIf).mockImplementationOnce(
      () =>
        new Promise<WhatIf>((resolve) => {
          release = resolve;
        }),
    );
    render(<DrillingPriceDrivers passportId="PASSPORT-1" params={params} />);
    await screen.findByText("260,00 ₽/м");

    const speed = slider("Техническая скорость станца".replace("станца", "станка"));
    fireEvent.pointerDown(speed);
    fireEvent.change(speed, { target: { value: "14" } });
    fireEvent.change(speed, { target: { value: "15" } });
    expect(api.blockEconomics.drillingWhatIf).not.toHaveBeenCalled();
    fireEvent.pointerUp(speed);

    await waitFor(() => expect(api.blockEconomics.drillingWhatIf).toHaveBeenCalledTimes(1));
    expect(api.blockEconomics.drillingWhatIf).toHaveBeenCalledWith("PASSPORT-1", params, { TECH_SPEED: 15 });
    expect(screen.getAllByText("считается…").length).toBe(2);

    release({
      base: drillingSensitivityFixture().base,
      result: { ...drillingSensitivityFixture().base, without_payroll_rub_per_m: 240, with_payroll_rub_per_m: 320 },
      reference_revision_id: "REV-1",
    });
    expect(await screen.findByText("240,00 ₽/м")).toBeInTheDocument();
    expect(screen.getByText("320,00 ₽/м")).toBeInTheDocument();
    expect(screen.getAllByText("−20,00 ₽/м к смете").length).toBe(2);
    expect(screen.queryByText("считается…")).toBeNull();

    const knob = speed.closest(".what-if-knob") as HTMLElement;
    expect(knob.classList.contains("is-changed")).toBe(true);
    fireEvent.click(within(knob).getByRole("button", { name: "Вернуть" }));
    // Пустые подмены — цена из ранжирования, второго запроса нет.
    expect(await screen.findByText("260,00 ₽/м")).toBeInTheDocument();
    expect(api.blockEconomics.drillingWhatIf).toHaveBeenCalledTimes(1);
    expect(screen.queryByText(/к смете/)).toBeNull();
  });

  it("при ставках шкала премии помечена как недействующая", async () => {
    vi.mocked(api.blockEconomics.drillingSensitivity).mockResolvedValue(drillingSensitivityFixture({ applies: false }));
    render(<DrillingPriceDrivers passportId="PASSPORT-1" params={{ ...params, payroll_source: "RATES" }} />);

    expect(await screen.findByText(/действует только при источнике ФОТ «Методика ФОТ»/)).toBeInTheDocument();
    const norm = slider("Норма за смену");
    expect((norm.closest(".what-if-knob") as HTMLElement).classList.contains("is-inactive")).toBe(true);
    // У недействующей ручки эффект не показывается.
    const head = (norm.closest(".what-if-knob") as HTMLElement).querySelector(".what-if-knob-effect");
    expect(head?.textContent ?? "").toBe("");
  });

  it("границы шкалы премии: потолок не ниже нормы + 1, расценка на потолке не ниже расценки на норме", async () => {
    render(<DrillingPriceDrivers passportId="PASSPORT-1" params={params} />);
    await screen.findByText("260,00 ₽/м");

    // Норма 115, потолок 185: норма не выше 184, потолок не ниже 116.
    expect(Number(slider("Норма за смену").max)).toBe(whatIfRange(115, undefined, 184).max);
    expect(Number(slider("Потолок за смену").min)).toBe(whatIfRange(185, 116).min);
    // Расценки 45 и 169: ±30 % не упираются в соседа, границы — от диапазона.
    expect(Number(slider("Расценка на норме").max)).toBe(whatIfRange(45, undefined, 169).max);
    expect(Number(slider("Расценка на потолке").min)).toBe(whatIfRange(169, 45).min);
  });

  it("ошибка сервера (422 по шкале) показывается текстом, а прежний результат не выдаётся за актуальный", async () => {
    render(<DrillingPriceDrivers passportId="PASSPORT-1" params={params} />);
    await screen.findByText("260,00 ₽/м");
    // Первая подмена удалась: на экране 240 и разница к смете.
    const speed = slider("Техническая скорость станка");
    fireEvent.change(speed, { target: { value: "15" } });
    fireEvent.pointerUp(speed);
    await screen.findByText("240,00 ₽/м");

    vi.mocked(api.blockEconomics.drillingWhatIf).mockRejectedValueOnce(
      new Error("Шкала премии не проходит проверку справочника: ceiling_per_shift: Потолок должен быть выше нормы"),
    );
    const rate = slider("Расценка на норме");
    fireEvent.change(rate, { target: { value: "50" } });
    fireEvent.pointerUp(rate);

    expect(await screen.findByRole("alert")).toHaveTextContent("Потолок должен быть выше нормы");
    expect(screen.queryByText("считается…")).toBeNull();
    // Старые 240 ₽/м и «к смете» ушли: цены недоступны, пока ручки не согласованы.
    expect(screen.queryByText("240,00 ₽/м")).toBeNull();
    expect(screen.queryByText(/к смете/)).toBeNull();
    expect(screen.getAllByText("—").length).toBe(2);

    // «Вернуть» сломавшую ручку — подмены снова считаются, ошибка уходит.
    const knob = rate.closest(".what-if-knob") as HTMLElement;
    fireEvent.click(within(knob).getByRole("button", { name: "Вернуть" }));
    expect(await screen.findByText("240,00 ₽/м")).toBeInTheDocument();
    expect(screen.queryByRole("alert")).toBeNull();
  });
});

describe("DrillingPriceDrivers: смена черновика", () => {
  it("пока ранжирование по новому черновику не пришло, цены помечены «считается…», а подмены исчезнувших ручек снимаются", async () => {
    const { rerender } = render(<DrillingPriceDrivers passportId="PASSPORT-1" params={params} />);
    await screen.findByText("260,00 ₽/м");
    const bit = slider("Цена дизельного топлива");
    fireEvent.change(bit, { target: { value: "60000" } });
    fireEvent.pointerUp(bit);
    await waitFor(() => expect(api.blockEconomics.drillingWhatIf).toHaveBeenCalledTimes(1));
    await screen.findByText("240,00 ₽/м");

    // Новый черновик: ранжирование без цены ДТ (объект без цены топлива).
    const next = drillingSensitivityFixture();
    next.knobs = next.knobs.filter((knob) => knob.code !== "DIESEL_PRICE");
    vi.mocked(api.blockEconomics.drillingSensitivity).mockResolvedValueOnce(next);
    rerender(<DrillingPriceDrivers passportId="PASSPORT-1" params={{ ...params, rig_code: "RIG_OTHER" }} />);
    expect(await screen.findAllByText("считается…")).toHaveLength(2);

    await waitFor(() => expect(api.blockEconomics.drillingSensitivity).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(screen.queryByText("считается…")).toBeNull());
    expect(screen.queryByRole("slider", { name: "Цена дизельного топлива" })).toBeNull();
    // Подмена снята: цена — из ранжирования, запроса «что если» по пустым подменам нет.
    expect(screen.getByText("260,00 ₽/м")).toBeInTheDocument();
    expect(screen.queryByText(/к смете/)).toBeNull();
  });
});

describe("premiumBounds", () => {
  it("считает границы по пробным значениям соседних ручек", () => {
    const knobs = drillingSensitivityFixture().premium!.knobs;
    expect(premiumBounds(knobs, {})).toEqual({
      PREMIUM_NORM: { max: 184 },
      PREMIUM_CEILING: { min: 116 },
      PREMIUM_RATE_NORM: { max: 169 },
      PREMIUM_RATE_CEILING: { min: 45 },
    });
    expect(premiumBounds(knobs, { PREMIUM_CEILING: 150, PREMIUM_RATE_NORM: 60 })).toEqual({
      PREMIUM_NORM: { max: 149 },
      PREMIUM_CEILING: { min: 116 },
      PREMIUM_RATE_NORM: { max: 169 },
      PREMIUM_RATE_CEILING: { min: 60 },
    });
    expect(premiumBounds([], {})).toEqual({});
  });
});

describe("whatIfRange", () => {
  it("±30 % со шагом «круглого» числа, нижняя граница не ниже шага, внешние границы сжимают", () => {
    expect(whatIfRange(12)).toEqual({ min: 8.4, max: 15.6, step: 0.2 });
    expect(whatIfRange(52200)).toEqual({ min: 37000, max: 68000, step: 1000 });
    expect(whatIfRange(1)).toEqual({ min: 0.7, max: 1.3, step: 0.01 });
    expect(whatIfRange(115, undefined, 100)).toEqual({ min: 80, max: 100, step: 2 });
    expect(whatIfRange(185, 190)).toEqual({ min: 190, max: 240, step: 2 });
    // Сумма на блок: шаг и размах ручки — от шага до двойной суммы.
    expect(whatIfRange(100000, undefined, undefined, { step: 20000, span: 1 })).toEqual({ min: 20000, max: 200000, step: 20000 });
  });
});

describe("DrillingPriceDrivers: ручки участка", () => {
  it("бегунок услуги шлёт подмену по её коду", async () => {
    render(<DrillingPriceDrivers passportId="PASSPORT-1" params={params} />);
    await screen.findByText("260,00 ₽/м");
    const trawl = slider("Услуги трала");
    // Шаг ручки — 20 000 ₽, диапазон — от шага до двойной суммы.
    expect([trawl.step, trawl.min, trawl.max]).toEqual(["20000", "20000", "140000"]);
    fireEvent.change(trawl, { target: { value: "80000" } });
    fireEvent.pointerUp(trawl);
    await waitFor(() =>
      expect(api.blockEconomics.drillingWhatIf).toHaveBeenCalledWith("PASSPORT-1", params, { "RULE:RULE_TRAWL": 80000 }),
    );
  });
});

describe("scaleChanged", () => {
  const curve = drillingSensitivityFixture().base.premium_curve!;

  it("та же шкала при другом темпе не считается сдвинутой, хотя ряд другой", () => {
    // Темп 132 вставлен в ряд и растянул его — шкала прежняя.
    const moved = {
      ...curve,
      pace: 132,
      series: [...curve.series, { pace: 132, rate: 999, per_shift: 0 }, { pace: 400, rate: 999, per_shift: 0 }],
    };
    expect(scaleChanged(curve, moved)).toBe(false);
  });

  it("ставка в общей точке темпа сдвинута — шкала изменена (так видны расценки ступеней)", () => {
    const changed = { ...curve, series: curve.series.map((point, index) => (index === 1 ? { ...point, rate: point.rate + 5 } : point)) };
    expect(scaleChanged(curve, changed)).toBe(true);
    expect(scaleChanged(curve, { ...curve, scale: { ...curve.scale, rate_norm: 60 } })).toBe(true);
  });
});
