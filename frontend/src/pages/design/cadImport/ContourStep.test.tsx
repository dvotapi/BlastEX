// @vitest-environment jsdom
// Шаг «Контур»: способ, его поля, площади и сверка с блоковой картой.
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { initialContour, type ContourState } from "./contourState";
import { ContourStep, type ContourStepProps } from "./ContourStep";
import { CAD_META, cadSource, contourResult } from "./testing/fixtures";

afterEach(cleanup);

const SOURCE = cadSource();

function renderStep(extra: Partial<ContourStepProps> = {}) {
  const props: ContourStepProps = {
    source: SOURCE,
    meta: CAD_META,
    state: initialContour(SOURCE),
    onChange: vi.fn(),
    result: contourResult(),
    pending: false,
    error: "",
    burden: 4,
    disabled: false,
    ...extra,
  };
  render(<ContourStep {...props} />);
  return props;
}

function lastState(props: ContourStepProps): ContourState {
  const calls = (props.onChange as ReturnType<typeof vi.fn>).mock.calls;
  return calls[calls.length - 1][0];
}

describe("ContourStep", () => {
  it("по умолчанию — готовый контур блока из чертежа", () => {
    renderStep();

    expect(screen.getByRole("radio", { name: "Готовый" }).getAttribute("aria-checked")).toBe("true");
    expect((screen.getByLabelText("Замкнутая линия") as HTMLSelectElement).value).toBe("769");
  });

  it("площади обоих контуров и средняя, периметр и фланги", () => {
    renderStep();

    const areas = screen.getByRole("group", { name: "Площади" });
    expect(within(areas).getByText("S верх").nextSibling?.textContent).toContain("2789,9 м²");
    expect(within(areas).getByText("S низ").nextSibling?.textContent).toContain("4120,9 м²");
    expect(within(areas).getByText("S ср").nextSibling?.textContent).toContain("3455,4 м²");
    expect(within(areas).getByText("Периметр").nextSibling?.textContent).toContain("341,1 м");
    expect(screen.getByText(/Фланги продлены до нижней бровки: 5,3 и 16,9 м/)).toBeTruthy();
  });

  it("площадь с блоковой карты даёт расхождение каждой площади", () => {
    renderStep({ state: { ...initialContour(SOURCE), mapArea: "2772,49" } });

    const areas = screen.getByRole("group", { name: "Площади" });
    expect(within(areas).getByText("S верх").nextSibling?.textContent).toContain("+0,63 %");
    expect(within(areas).getByText("S ср").nextSibling?.textContent).toContain("+24,63 %");
  });

  it("смена способа", () => {
    const props = renderStep();

    fireEvent.click(screen.getByRole("radio", { name: "Сборка" }));

    expect(lastState(props).method).toBe("assembly");
  });

  it("сборка: список участков и кнопки правки", () => {
    const state: ContourState = {
      ...initialContour(SOURCE),
      method: "assembly",
      items: [
        { kind: "part", handle: "6C3", start_m: 0, end_m: 30, points: [], flip: false, label: "" },
        { kind: "part", handle: "733", start_m: 0, end_m: 30, points: [], flip: false, label: "" },
      ],
      selected: 0,
    };
    const props = renderStep({
      state,
      result: contourResult({
        method: "assembly",
        ok: false,
        item_info: [
          { kind: "part", handle: "6C3", layer: "Горизонт +410", length_m: 30.4, reversed: false, gap_to_next_m: 18.6, link: "closing" },
          { kind: "part", handle: "733", layer: "Горизонт +410", length_m: 30.1, reversed: true, gap_to_next_m: 75.3, link: "closing" },
        ],
      }),
    });

    expect(screen.getByRole("table", { name: "Участки контура" })).toBeTruthy();
    expect(screen.getByText("замыкающий 18,60 м")).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "Развернуть" }));
    expect(lastState(props).items[0].flip).toBe(true);
    fireEvent.click(screen.getByRole("button", { name: "Удалить" }));
    expect(lastState(props).items.map((item) => item.handle)).toEqual(["733"]);
    fireEvent.click(screen.getByRole("button", { name: "Отменить" }));
    expect(lastState(props).items.map((item) => item.handle)).toEqual(["6C3"]);
    fireEvent.click(screen.getByRole("radio", { name: "Отрезок" }));
    expect(lastState(props).tool).toBe("segment");
  });

  it("результат готового контура можно править как сборку", () => {
    const props = renderStep();

    fireEvent.click(screen.getByRole("button", { name: "Править как сборку" }));

    expect(lastState(props)).toMatchObject({ method: "assembly", items: contourResult().items });
  });

  it("блок по бровке: ширина рядами × W из паспорта", () => {
    const props = renderStep({ state: { ...initialContour(SOURCE), method: "crest", widthMode: "rows" } });

    expect(screen.getByText(/× W 4,0 м = 20,0 м/)).toBeTruthy();
    fireEvent.change(screen.getByLabelText("Рядов"), { target: { value: "6" } });
    expect(lastState(props).rows).toBe("6");
  });

  it("щелчок внутри: роли линий контура и мост", () => {
    const props = renderStep({ state: { ...initialContour(SOURCE), method: "click" } });

    fireEvent.click(screen.getByRole("checkbox", { name: "Характерная линия" }));
    expect(lastState(props).roles).toContain("feature_line");
    fireEvent.change(screen.getByLabelText("Мост до, м"), { target: { value: "3" } });
    expect(lastState(props).bridge).toBe("3");
  });
});

describe("ContourStep: слишком много линий для разрезов", () => {
  const note = "Линий выбранных ролей слишком много: 30000 отрезков, предел 20000. Снимите лишние роли.";

  it("видно в сборке и щелчке внутри", () => {
    renderStep({ state: { ...initialContour(SOURCE), method: "assembly" }, splitsError: note });
    expect(screen.getByText(note)).toBeTruthy();
  });

  it("не мешает готовому контуру и блоку по бровке", () => {
    renderStep({ splitsError: note });
    expect(screen.queryByText(note)).toBeNull();
    cleanup();
    renderStep({ state: { ...initialContour(SOURCE), method: "crest" }, splitsError: note });
    expect(screen.queryByText(note)).toBeNull();
  });
});

it("пока предпросмотр считается, сведения участков не показываются (они от прошлого списка)", () => {
  const state: ContourState = {
    ...initialContour(SOURCE),
    method: "assembly",
    items: [{ kind: "part", handle: "6C3", start_m: 0, end_m: 30, points: [], flip: false, label: "" }],
  };
  renderStep({
    state,
    pending: true,
    result: contourResult({
      method: "assembly",
      item_info: [{ kind: "part", handle: "733", layer: "Горизонт +410", length_m: 42.4, reversed: true, gap_to_next_m: 75.3, link: "closing" }],
    }),
  });
  expect(screen.queryByText("замыкающий 75,30 м")).toBeNull();
});


describe("ContourStep: площадь блока по соглашению маркшейдера", () => {
  it("по умолчанию площадь блока — S ср, её можно сменить", () => {
    const props = renderStep();

    const group = screen.getByRole("radiogroup", { name: "Площадь блока" });
    expect((within(group).getByRole("radio", { name: /S ср/ }) as HTMLInputElement).checked).toBe(true);

    fireEvent.click(within(group).getByRole("radio", { name: /S верх/ }));

    expect(lastState(props).areaBasis).toBe("top");
  });
});
