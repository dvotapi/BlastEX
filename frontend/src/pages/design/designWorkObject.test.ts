import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

/**
 * Объект работ для настроек Kuz-Ram «Проектирование» берёт сервер — активный
 * объект организации. Имя из закэшированного состояния шапки могло устареть,
 * и тогда панель «Кусковатость» и паспорт сохранённого плана (сервер берёт
 * свой объект) считали бы по разным настройкам. Поэтому страница имя объекта
 * не передаёт ни в одном запросе. Сверяем исходник: рендер страницы целиком
 * требует десятков заглушек API и не проверил бы все шесть запросов разом.
 */
describe("DesignPage и объект работ", () => {
  it("не передаёт work_object_name и не читает объект из шапки", () => {
    const source = readFileSync(new URL("./DesignPage.tsx", import.meta.url), "utf8");
    expect(source).not.toMatch(/work_object_name/);
    expect(source).not.toMatch(/useWorkspace/);
    expect(source).not.toMatch(/active_work_object_name/);
  });
});
