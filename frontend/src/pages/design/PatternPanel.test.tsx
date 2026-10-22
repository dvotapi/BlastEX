// @vitest-environment jsdom
// Вкладка «Сетка»: поля наклона рядов у откоса пишут ключи в параметры только
// когда пользователь их задал.
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { DEFAULT_PATTERN_PARAMS, type PatternParams } from "../../types/design";
import { PatternPanel } from "./PatternPanel";

afterEach(cleanup);

function mount(params: PatternParams = DEFAULT_PATTERN_PARAMS) {
  const onChange = vi.fn();
  render(<PatternPanel params={params} onChange={onChange} onGenerate={() => {}} busy={false} />);
  return onChange;
}

describe("PatternPanel: наклон рядов у откоса", () => {
  it("по умолчанию 0 рядов и поле угла скрыто", () => {
    mount();
    expect((screen.getByLabelText("Наклонных рядов у откоса") as HTMLSelectElement).value).toBe("0");
    expect(screen.queryByLabelText("Наклон рядов у откоса, ° от вертикали")).toBeNull();
  });

  it("выбор 2 пишет front_rows_tilt_count: 2", () => {
    const onChange = mount();
    fireEvent.change(screen.getByLabelText("Наклонных рядов у откоса"), { target: { value: "2" } });
    expect(onChange).toHaveBeenCalledWith({ front_rows_tilt_count: 2 });
  });

  it("при рядах > 0 угол виден, по умолчанию 15, ввод 40 пишется как 30", () => {
    const onChange = mount({ ...DEFAULT_PATTERN_PARAMS, front_rows_tilt_count: 1 });
    const field = screen.getByLabelText("Наклон рядов у откоса, ° от вертикали") as HTMLInputElement;
    expect(field.value).toBe("15");
    fireEvent.change(field, { target: { value: "40" } });
    expect(onChange).toHaveBeenCalledWith({ front_rows_tilt_deg: 30 });
  });

  it("выбор 0 убирает оба ключа наклона", () => {
    const onChange = mount({ ...DEFAULT_PATTERN_PARAMS, front_rows_tilt_count: 2, front_rows_tilt_deg: 20 });
    fireEvent.change(screen.getByLabelText("Наклонных рядов у откоса"), { target: { value: "0" } });
    expect(onChange).toHaveBeenCalledWith({ front_rows_tilt_count: undefined, front_rows_tilt_deg: undefined });
  });
});
