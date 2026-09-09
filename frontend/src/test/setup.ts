import "@testing-library/jest-dom/vitest";
import { vi } from "vitest";

// jsdom не реализует `scrollIntoView` — `selectGroupFromChart` в
// `BlockEconomicsPage.tsx` зовёт его при клике по сегменту диаграммы.
// Тесты с `environment: "node"` (по умолчанию в этом проекте) этот файл
// тоже подключают — без `window` там писать некуда.
if (typeof window !== "undefined") {
  window.HTMLElement.prototype.scrollIntoView = vi.fn();
}
