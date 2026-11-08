// @vitest-environment jsdom
import { act } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, describe, expect, it, vi } from "vitest";

import { WhatIfSlider } from "./WhatIfSlider";

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean | undefined;
}

const containers: HTMLElement[] = [];

afterEach(() => {
  containers.splice(0).forEach((el) => el.remove());
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
});

/** Значение бегунка, как его ставит браузер: через сеттер прототипа, чтобы React увидел изменение. */
function setRangeValue(input: HTMLInputElement, value: string) {
  const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!;
  setter.call(input, value);
  input.dispatchEvent(new Event("input", { bubbles: true }));
}

describe("WhatIfSlider", () => {
  it("движение сразу после появления бегунка не теряется: эффект монтирования не сбрасывает его", async () => {
    // Бегунки появляются с ответом сервера (коммит вне act), а тест ловит их
    // по изменению DOM — раньше, чем React выполнит пассивные эффекты
    // монтирования. Событие внутри act сначала выполняет эти эффекты, и прежний
    // сброс «при смене value/base» на монтировании стирал только что сдвинутое
    // значение и таймер: пробный расчёт не запускался (флак CI 63a7e9d).
    globalThis.IS_REACT_ACT_ENVIRONMENT = false;
    const container = document.createElement("div");
    document.body.appendChild(container);
    containers.push(container);
    const onChange = vi.fn();
    const root = createRoot(container);
    const mounted = new Promise<void>((resolve) => {
      const observer = new MutationObserver(() => {
        observer.disconnect();
        resolve();
      });
      observer.observe(container, { childList: true, subtree: true });
    });
    root.render(<WhatIfSlider code="SPEED" label="Скорость" unit="м/ч" base={12} value={null} onChange={onChange} />);
    await mounted;
    const input = container.querySelector("input[type=range]") as HTMLInputElement;
    globalThis.IS_REACT_ACT_ENVIRONMENT = true;
    act(() => setRangeValue(input, "13"));
    act(() => {
      input.dispatchEvent(new Event("pointerup", { bubbles: true }));
    });
    expect(onChange).toHaveBeenCalledWith(13);
    act(() => root.unmount());
  });
});
