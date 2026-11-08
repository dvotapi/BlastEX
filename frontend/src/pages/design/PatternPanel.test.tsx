// @vitest-environment jsdom
// Вкладка «Сетка»: поля наклона рядов у откоса пишут ключи в параметры только
// когда пользователь их задал.
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { api } from "../../api/endpoints";
import { DEFAULT_PATTERN_PARAMS, type BlockContour, type PatternParams } from "../../types/design";
import { PatternPanel } from "./PatternPanel";

vi.mock("../../api/endpoints", () => ({ api: { design: { backAzimuth: vi.fn() } } }));

afterEach(cleanup);

function mount(params: PatternParams = DEFAULT_PATTERN_PARAMS) {
  const onChange = vi.fn();
  render(<PatternPanel params={params} onChange={onChange} onGenerate={() => {}} busy={false} />);
  return onChange;
}

const SCHEME = "Первый ряд у откоса";
const TILT = "Разрешить наклон пары";
const TAPER_TILT = "Наибольший наклон, ° от вертикали";
const BACK_TILT = "Предпочтительный наклон, ° от вертикали";
const RECT: PatternParams = { ...DEFAULT_PATTERN_PARAMS, pattern: "rectangular" };
const STAGGERED_HINT = /не применяется к шахматной сетке/;

function taperOption(): HTMLOptionElement {
  return screen.getByRole("option", { name: /Плавный переход/ }) as HTMLOptionElement;
}

describe("PatternPanel: первый ряд у откоса", () => {
  it("по умолчанию «Вертикальный», поля скрыты", () => {
    mount();
    expect((screen.getByLabelText(SCHEME) as HTMLSelectElement).value).toBe("vertical");
    expect(screen.queryByLabelText(TILT)).toBeNull();
    expect(screen.queryByLabelText(TAPER_TILT)).toBeNull();
    expect(screen.queryByLabelText("Рядов перехода")).toBeNull();
  });

  it("«Пара» пишет front_rows_mode: pair и показывает угол без числа рядов", () => {
    const onChange = mount();
    fireEvent.change(screen.getByLabelText(SCHEME), { target: { value: "pair" } });
    expect(onChange).toHaveBeenCalledWith({ front_rows_mode: "pair", front_rows_tilt_count: undefined });
    cleanup();
    mount({ ...DEFAULT_PATTERN_PARAMS, front_rows_mode: "pair" });
    expect(screen.getByLabelText(TILT)).toBeTruthy();
    expect(screen.queryByLabelText("Рядов перехода")).toBeNull();
  });

  it("«Плавный переход» пишет taper и показывает «Рядов перехода»", () => {
    const onChange = mount(RECT);
    fireEvent.change(screen.getByLabelText(SCHEME), { target: { value: "taper" } });
    expect(onChange).toHaveBeenCalledWith({ front_rows_mode: "taper", front_rows_tilt_count: 1 });
    cleanup();
    const onChange2 = mount({ ...RECT, front_rows_mode: "taper", front_rows_tilt_count: 1 });
    fireEvent.change(screen.getByLabelText("Рядов перехода"), { target: { value: "2" } });
    expect(onChange2).toHaveBeenCalledWith({ front_rows_tilt_count: 2 });
  });

  it("старый паспорт только с front_rows_tilt_count показывается как «Плавный переход»", () => {
    mount({ ...RECT, front_rows_tilt_count: 2 });
    expect((screen.getByLabelText(SCHEME) as HTMLSelectElement).value).toBe("taper");
    expect((screen.getByLabelText("Рядов перехода") as HTMLSelectElement).value).toBe("2");
  });

  it("угол перехода по умолчанию 15, ввод 40 пишется как 30", () => {
    const onChange = mount({ ...RECT, front_rows_mode: "taper", front_rows_tilt_count: 1 });
    const field = screen.getByLabelText(TAPER_TILT) as HTMLInputElement;
    expect(field.value).toBe("");
    expect(field.placeholder).toBe("15");
    fireEvent.change(field, { target: { value: "40" } });
    expect(onChange).toHaveBeenCalledWith({ front_rows_tilt_deg: 30 });
  });

  it("пустой наклон убирает ключ, а не пишет 0", () => {
    const onChange = mount({ ...RECT, front_rows_mode: "taper", front_rows_tilt_count: 1, front_rows_tilt_deg: 20 });
    fireEvent.change(screen.getByLabelText(TAPER_TILT), { target: { value: "" } });
    const [patch] = onChange.mock.calls[0];
    expect("front_rows_tilt_deg" in patch).toBe(true);
    expect(patch.front_rows_tilt_deg).toBeUndefined();
  });

  it("«Вертикальный» убирает ключи схемы и отступа", () => {
    const onChange = mount({ ...DEFAULT_PATTERN_PARAMS, front_rows_mode: "taper", front_rows_tilt_count: 2, front_rows_tilt_deg: 20, min_crest_offset_m: 2 });
    fireEvent.change(screen.getByLabelText(SCHEME), { target: { value: "vertical" } });
    const [patch] = onChange.mock.calls[0];
    expect(Object.keys(patch).sort()).toEqual(["front_rows_mode", "front_rows_tilt_count", "front_rows_tilt_deg", "min_crest_offset_m"]);
    expect(Object.values(patch).every((v) => v === undefined)).toBe(true);
  });

  it("у вертикального первого ряда отступа от кромки нет, если он не задан", () => {
    mount();
    expect(screen.queryByLabelText("Мин. отступ устья от кромки, м")).toBeNull();
    cleanup();
    mount({ ...DEFAULT_PATTERN_PARAMS, min_crest_offset_m: 1.5 });
    expect((screen.getByLabelText("Мин. отступ устья от кромки, м") as HTMLInputElement).value).toBe("1.5");
  });

  it("«Мин. отступ устья от кромки» пишет ключ, умолчание 1 — подсказка", () => {
    const onChange = mount({ ...DEFAULT_PATTERN_PARAMS, front_rows_mode: "pair" });
    const field = screen.getByLabelText("Мин. отступ устья от кромки, м") as HTMLInputElement;
    expect(field.value).toBe("");
    expect(field.placeholder).toBe("0,2");
    fireEvent.change(field, { target: { value: "1.5" } });
    expect(onChange).toHaveBeenCalledWith({ min_crest_offset_m: 1.5 });
  });

  it("вид «Наклонная у откоса» не предлагается для сетки", () => {
    mount();
    expect(screen.queryByText("Наклонная у откоса")).toBeNull();
  });

  it("у шахматной сетки «Плавный переход» недоступен, у прямоугольной — доступен", () => {
    expect(DEFAULT_PATTERN_PARAMS.pattern).toBe("staggered");
    mount();
    expect(taperOption().disabled).toBe(true);
    expect(taperOption().textContent).toMatch(STAGGERED_HINT);
    expect(screen.queryByRole("note")).toBeNull();
    cleanup();
    mount(RECT);
    expect(taperOption().disabled).toBe(false);
    expect(taperOption().textContent).not.toMatch(STAGGERED_HINT);
  });

  it("сохранённый taper у шахматной сетки — неактивен с подсказкой, параметры не переписываются", () => {
    const onChange = mount({ ...DEFAULT_PATTERN_PARAMS, front_rows_mode: "taper", front_rows_tilt_count: 2 });
    expect((screen.getByLabelText(SCHEME) as HTMLSelectElement).value).toBe("taper");
    expect((screen.getByLabelText("Рядов перехода") as HTMLSelectElement).disabled).toBe(true);
    expect(screen.getByRole("note").textContent).toMatch(STAGGERED_HINT);
    expect(onChange).not.toHaveBeenCalled();
  });

  it("переключение на шахматную при выбранном переходе показывает подсказку", () => {
    const params: PatternParams = { ...RECT, front_rows_mode: "taper", front_rows_tilt_count: 1 };
    const onChange = vi.fn();
    const { rerender } = render(<PatternPanel params={params} onChange={onChange} onGenerate={() => {}} busy={false} />);
    expect(screen.queryByRole("note")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: /Шахматная/ }));
    expect(onChange).toHaveBeenCalledWith({ pattern: "staggered" });
    rerender(<PatternPanel params={{ ...params, pattern: "staggered" }} onChange={onChange} onGenerate={() => {}} busy={false} />);
    expect(screen.getByRole("note").textContent).toMatch(STAGGERED_HINT);
    expect(onChange).toHaveBeenCalledTimes(1);
  });
});

describe("PatternPanel: шаг b у квадратной сетки", () => {
  it("квадрат — и без вида сетки (старый паспорт): b заблокирован и равен a", () => {
    for (const pattern of ["square", undefined, "непонятный"]) {
      mount({ ...DEFAULT_PATTERN_PARAMS, pattern, spacing_a_m: 4.6, burden_b_m: 3.7 } as unknown as PatternParams);
      const b = screen.getByLabelText("Шаг между рядами b, м") as HTMLInputElement;
      expect(b.disabled).toBe(true);
      expect(b.value).toBe("4.6");
      cleanup();
    }
    mount({ ...RECT, spacing_a_m: 4.6, burden_b_m: 3.7 });
    const b = screen.getByLabelText("Шаг между рядами b, м") as HTMLInputElement;
    expect(b.disabled).toBe(false);
    expect(b.value).toBe("3.7");
  });
  it("у пары — флажок «Разрешить наклон пары»: снят пишет 0, поставлен убирает ключ", () => {
    const onChange = mount({ ...DEFAULT_PATTERN_PARAMS, front_rows_mode: "pair" });
    const box = screen.getByLabelText(TILT) as HTMLInputElement;
    expect(box.type).toBe("checkbox");
    expect(box.checked).toBe(true);
    expect((box.closest("label") as HTMLLabelElement).title).toContain("к кромке");
    expect(screen.queryByLabelText(TAPER_TILT)).toBeNull();
    fireEvent.click(box);
    expect(onChange).toHaveBeenCalledWith({ front_rows_tilt_deg: 0 });
    cleanup();
    const onChange2 = mount({ ...DEFAULT_PATTERN_PARAMS, front_rows_mode: "pair", front_rows_tilt_deg: 0 });
    const off = screen.getByLabelText(TILT) as HTMLInputElement;
    expect(off.checked).toBe(false);
    fireEvent.click(off);
    const [patch] = onChange2.mock.calls[0];
    expect("front_rows_tilt_deg" in patch).toBe(true);
    expect(patch.front_rows_tilt_deg).toBeUndefined();
  });

  it("у плавного перехода наклон по-прежнему наибольший", () => {
    mount({ ...RECT, front_rows_mode: "taper", front_rows_tilt_count: 1 });
    expect(screen.getByLabelText(TAPER_TILT)).toBeTruthy();
  });
  it("глубина коротких — по вертикали: у наклонной длина по оси больше", () => {
    mount({ ...DEFAULT_PATTERN_PARAMS, stab_row: true });
    const field = screen.getByLabelText("Глубина коротких (по вертикали), м");
    expect((field.closest("label") as HTMLLabelElement).title).toContain("cos α");
  });
});

const ANCHOR = "Опора сетки";
const BACK_OFFSET = "Отступ от тыла, м";
const BACK_LOCK = "Без поворота рядов от тыла";
const CONTOUR: BlockContour = {
  vertices: [
    { x: 0, y: 0, z: 0 },
    { x: 40, y: 0, z: 0 },
    { x: 40, y: 22, z: 0 },
    { x: 0, y: 22, z: 0 },
  ],
  free_faces: [[0, 1]],
  bench: { crest_z_m: 0, toe_z_m: -10, face_angle_deg: 75 },
  name: "Блок",
};

function mountWithContour(params: PatternParams, contour: BlockContour | null = CONTOUR) {
  const onChange = vi.fn();
  render(<PatternPanel params={params} onChange={onChange} onGenerate={() => {}} busy={false} contour={contour} />);
  return onChange;
}

describe("PatternPanel: опора сетки «от тыла»", () => {
  it("«от тыла» пишет layout_anchor: back и азимут рядов по тылу", async () => {
    vi.mocked(api.design.backAzimuth).mockReset().mockResolvedValue({ azimuth_deg: 93.5 });
    const onChange = mountWithContour(RECT);
    const select = screen.getByLabelText(ANCHOR) as HTMLSelectElement;
    expect(select.value).toBe("crest");
    fireEvent.change(select, { target: { value: "back" } });
    await waitFor(() => expect(onChange).toHaveBeenCalledWith({ layout_anchor: "back", row_azimuth_deg: 93.5 }));
    expect(api.design.backAzimuth).toHaveBeenCalledWith(CONTOUR);
  });

  it("тыла нет (ответ null) — опора пишется, азимут не меняется", async () => {
    vi.mocked(api.design.backAzimuth).mockReset().mockResolvedValue({ azimuth_deg: null });
    const onChange = mountWithContour(RECT);
    fireEvent.change(screen.getByLabelText(ANCHOR), { target: { value: "back" } });
    await waitFor(() => expect(onChange).toHaveBeenCalledWith({ layout_anchor: "back" }));
  });

  it("«от бровки» убирает ключи опоры и отступа", () => {
    const onChange = mountWithContour({ ...RECT, layout_anchor: "back", back_offset_m: 2 });
    fireEvent.change(screen.getByLabelText(ANCHOR), { target: { value: "crest" } });
    const [patch] = onChange.mock.calls[0];
    expect(Object.keys(patch).sort()).toEqual(["back_offset_m", "back_turn_locked", "layout_anchor"]);
    expect(Object.values(patch).every((v) => v === undefined)).toBe(true);
  });

  it("у шахматной, переменной и по доменам выбора нет", () => {
    for (const pattern of ["staggered", "variable", "domain_dependent"] as const) {
      mountWithContour({ ...DEFAULT_PATTERN_PARAMS, pattern });
      expect(screen.queryByLabelText(ANCHOR)).toBeNull();
      cleanup();
    }
    mountWithContour({ ...DEFAULT_PATTERN_PARAMS, pattern: "square" });
    expect(screen.getByLabelText(ANCHOR)).toBeTruthy();
  });

  it("без контура «от тыла» недоступно", () => {
    mountWithContour(RECT, null);
    const option = screen.getByRole("option", { name: /^От тыла/ }) as HTMLOptionElement;
    expect(option.disabled).toBe(true);
    cleanup();
    mountWithContour(RECT, { ...CONTOUR, vertices: CONTOUR.vertices.slice(0, 2) });
    expect((screen.getByRole("option", { name: /^От тыла/ }) as HTMLOptionElement).disabled).toBe(true);
  });

  it("«Отступ от тыла»: подсказка 20·d", () => {
    const onChange = mountWithContour({ ...RECT, burden_b_m: 4, diameter_mm: 145, layout_anchor: "back" });
    const field = screen.getByLabelText(BACK_OFFSET) as HTMLInputElement;
    expect(field.value).toBe("");
    // 20 × 0,145 = 2,9 м — не зависит от b.
    expect(field.placeholder).toBe("2,9");
    expect((field.closest("label") as HTMLLabelElement).title).toMatch(/20·d/);
    expect((field.closest("label") as HTMLLabelElement).title).not.toMatch(/разбуривания/);
    expect(onChange).not.toHaveBeenCalled();
  });

  it("«от тыла» прячет поля шаблона от бровки; «Отступ от контура» остаётся", () => {
    const CREST_ONLY = ["Отступ от откоса, м", "ЛНС первого ряда, м", "Первый ряд повторяет открытый откос"];
    mountWithContour({ ...RECT, layout_anchor: "back" });
    for (const label of CREST_ONLY) expect(screen.queryByLabelText(label)).toBeNull();
    expect(screen.getByLabelText("Отступ от контура, м")).toBeTruthy();
    cleanup();
    mountWithContour(RECT);
    for (const label of CREST_ONLY) expect(screen.getByLabelText(label)).toBeTruthy();
    expect(screen.getByLabelText("Отступ от контура, м")).toBeTruthy();
  });

  it("«Отступ от тыла»: ввод пишет ключ, пусто убирает", () => {
    const onChange = mountWithContour({ ...RECT, burden_b_m: 4, layout_anchor: "back" });
    const field = screen.getByLabelText(BACK_OFFSET) as HTMLInputElement;
    fireEvent.change(field, { target: { value: "3" } });
    expect(onChange).toHaveBeenCalledWith({ back_offset_m: 3 });
    cleanup();
    const onChange2 = mountWithContour({ ...RECT, layout_anchor: "back", back_offset_m: 3 });
    fireEvent.change(screen.getByLabelText(BACK_OFFSET), { target: { value: "" } });
    const [patch] = onChange2.mock.calls[0];
    expect("back_offset_m" in patch).toBe(true);
    expect(patch.back_offset_m).toBeUndefined();
  });

  it("«Без поворота рядов от тыла»: галочка пишет ключ, снятая — убирает; от бровки её нет", () => {
    const onChange = mountWithContour({ ...RECT, layout_anchor: "back" });
    const box = screen.getByLabelText(BACK_LOCK) as HTMLInputElement;
    expect(box.checked).toBe(false);
    expect((box.closest("label") as HTMLLabelElement).title).toMatch(/подбор/i);
    fireEvent.click(box);
    expect(onChange).toHaveBeenCalledWith({ back_turn_locked: true });
    cleanup();
    const onChange2 = mountWithContour({ ...RECT, layout_anchor: "back", back_turn_locked: true });
    const box2 = screen.getByLabelText(BACK_LOCK) as HTMLInputElement;
    expect(box2.checked).toBe(true);
    fireEvent.click(box2);
    const [patch] = onChange2.mock.calls[0];
    expect("back_turn_locked" in patch && patch.back_turn_locked === undefined).toBe(true);
    cleanup();
    mountWithContour(RECT);
    expect(screen.queryByLabelText(BACK_LOCK)).toBeNull();
  });

  it("«Отступ от контура» у «от тыла» — подсказка: только боковые стороны", () => {
    mountWithContour({ ...RECT, layout_anchor: "back" });
    const back = (screen.getByLabelText("Отступ от контура, м").closest("label") as HTMLLabelElement).title;
    expect(back).toMatch(/боковым сторонам/);
    cleanup();
    mountWithContour(RECT);
    const crest = (screen.getByLabelText("Отступ от контура, м").closest("label") as HTMLLabelElement).title;
    expect(crest).not.toMatch(/боковым сторонам/);
  });

  it("«от тыла»: из первого ряда у откоса — только предпочтительный наклон и отступ от кромки", () => {
    mountWithContour({ ...RECT, layout_anchor: "back" });
    expect(screen.queryByLabelText(SCHEME)).toBeNull();
    expect(screen.queryByLabelText("Рядов перехода")).toBeNull();
    expect(screen.getByLabelText(BACK_TILT)).toBeTruthy();
    expect(screen.queryByLabelText(TILT)).toBeNull();
    expect(screen.getByLabelText("Мин. отступ устья от кромки, м")).toBeTruthy();
    expect(screen.queryByLabelText(BACK_OFFSET)).toBeTruthy();
  });

  it("«от тыла»: подсказка наклона — наименьший угол до ЛСП ≈ W", () => {
    mountWithContour({ ...RECT, layout_anchor: "back" });
    const title = (screen.getByLabelText(BACK_TILT).closest("label") as HTMLLabelElement).title;
    expect(title).toMatch(/наименьший/);
    expect(title).toMatch(/ЛСП ≈ W/);
  });

  it("«Азимут по тылу» ставит азимут рядов, без контура недоступна", async () => {
    vi.mocked(api.design.backAzimuth).mockReset().mockResolvedValue({ azimuth_deg: 12 });
    const onChange = mountWithContour({ ...RECT, layout_anchor: "back" });
    fireEvent.click(screen.getByRole("button", { name: "Азимут по тылу" }));
    await waitFor(() => expect(onChange).toHaveBeenCalledWith({ row_azimuth_deg: 12 }));
    cleanup();
    mountWithContour({ ...RECT, layout_anchor: "back" }, null);
    expect((screen.getByRole("button", { name: "Азимут по тылу" }) as HTMLButtonElement).disabled).toBe(true);
  });

  it("смена сетки на шахматную убирает ключи «от тыла»", () => {
    const onChange = mountWithContour({ ...RECT, layout_anchor: "back", back_offset_m: 2, back_turn_locked: true });
    fireEvent.click(screen.getByRole("button", { name: /Шахматная/ }));
    const [patch] = onChange.mock.calls[0];
    expect(patch.pattern).toBe("staggered");
    expect("back_turn_locked" in patch && patch.back_turn_locked === undefined).toBe(true);
    expect("layout_anchor" in patch && patch.layout_anchor === undefined).toBe(true);
    expect("back_offset_m" in patch && patch.back_offset_m === undefined).toBe(true);
    cleanup();
    const onChange2 = mountWithContour({ ...RECT, layout_anchor: "back" });
    fireEvent.click(screen.getByRole("button", { name: /Квадратная/ }));
    expect(onChange2).toHaveBeenCalledWith({ pattern: "square" });
  });

  it("ответ азимута после правки параметров не перезаписывает их", async () => {
    let resolve: (value: { azimuth_deg: number | null }) => void = () => {};
    vi.mocked(api.design.backAzimuth)
      .mockReset()
      .mockReturnValue(new Promise((r) => (resolve = r)));
    const onChange = vi.fn();
    const view = render(
      <PatternPanel params={RECT} onChange={onChange} onGenerate={() => {}} busy={false} contour={CONTOUR} />,
    );
    fireEvent.change(screen.getByLabelText(ANCHOR), { target: { value: "back" } });
    view.rerender(
      <PatternPanel
        params={{ ...RECT, row_azimuth_deg: 45 }}
        onChange={onChange}
        onGenerate={() => {}}
        busy={false}
        contour={CONTOUR}
      />,
    );
    resolve({ azimuth_deg: 93.5 });
    await waitFor(() => expect(onChange).toHaveBeenCalled());
    expect(onChange).toHaveBeenCalledWith({ layout_anchor: "back" });
    expect(onChange).not.toHaveBeenCalledWith(expect.objectContaining({ row_azimuth_deg: 93.5 }));
  });

  it("сохранённый «от тыла» у шахматной не показывается и не переписывается", () => {
    const onChange = mountWithContour({ ...DEFAULT_PATTERN_PARAMS, layout_anchor: "back" });
    expect(screen.queryByLabelText(ANCHOR)).toBeNull();
    expect(screen.getByLabelText(SCHEME)).toBeTruthy();
    expect(onChange).not.toHaveBeenCalled();
  });
});
