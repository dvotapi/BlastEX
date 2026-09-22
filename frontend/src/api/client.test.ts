import { describe, expect, it } from "vitest";
import { errorMessage } from "./client";

const response = (body: unknown, status = 422) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

describe("errorMessage", () => {
  it("422: русские тексты валидаторов API дописываются к общему, без повторов", async () => {
    const body = {
      detail: "Ошибка валидации входных данных.",
      details: [
        { loc: ["body", "facts", 1, "crown_mm"], msg: "Диаметр коронки — от 20 до 1000 мм.", type: "crown_mm" },
        { loc: ["body", "facts", 2, "crown_mm"], msg: "Диаметр коронки — от 20 до 1000 мм.", type: "crown_mm" },
        { loc: ["body", "kuzram"], msg: "Поправка C(A) — от 0,1 до 10.", type: "kuzram_settings" },
      ],
    };
    expect(await errorMessage(response(body), "запасной")).toBe(
      "Ошибка валидации входных данных: Диаметр коронки — от 20 до 1000 мм. Поправка C(A) — от 0,1 до 10.",
    );
  });

  it("английские тексты pydantic не показываются", async () => {
    const body = {
      detail: "Ошибка валидации входных данных.",
      details: [{ loc: ["body", "target", "lump_size_mm"], msg: "Input should be greater than 0", type: "greater_than" }],
    };
    expect(await errorMessage(response(body), "запасной")).toBe("Ошибка валидации входных данных.");
  });

  it("прежние форматы: строка detail, detail.message, ответ без JSON", async () => {
    expect(await errorMessage(response({ detail: "Фактор породы A = −0,5." }, 400), "запасной")).toBe("Фактор породы A = −0,5.");
    expect(await errorMessage(response({ detail: { message: "Нет доступа." } }, 403), "запасной")).toBe("Нет доступа.");
    expect(await errorMessage(new Response("oops", { status: 500 }), "запасной")).toBe("запасной");
  });
});
