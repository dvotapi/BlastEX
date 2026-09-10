// @vitest-environment jsdom
import { cleanup, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { renderWithWorkspace } from "../../test/render";

vi.mock("../../api/endpoints", () => ({
  api: {
    economics: {
      technicalPassports: vi.fn(),
      revisions: vi.fn(),
      referenceSnapshot: vi.fn(),
    },
    blockEconomics: {
      modelDefaults: vi.fn(),
      runs: vi.fn(),
      variants: vi.fn(),
      saveRun: vi.fn(),
      run: vi.fn(),
      sensitivity: vi.fn(),
      compare: vi.fn(),
      serviceToReference: vi.fn(),
      exportUrl: (id: string) => `/x/${id}`,
    },
  },
}));

import { api } from "../../api/endpoints";
import { BlockEconomicsPage } from "./BlockEconomicsPage";
import { money } from "./format";
import { defaultsFixture, economicsFixture } from "./testFixtures";
import type { BlockEconomics, EconomicsRun, EconomicsRunSummary, VariantsResponse } from "../../types/blockEconomics";

const PASSPORT = defaultsFixture().passport;

function variantsResponse(economics: BlockEconomics): VariantsResponse {
  return { reference_revision_id: "REV-1", variants: [{ name: "Вариант 1", economics }] };
}

/** Тот же расчёт, но с другой суммой строки основного ВВ — для проверки пересчёта. */
function withExplosiveAmount(amount: number): BlockEconomics {
  const economics = economicsFixture();
  return {
    ...economics,
    lines: economics.lines.map((line) =>
      line.cost_item_code === "MATERIAL_EXPLOSIVE" ? { ...line, amount_rub: amount } : line,
    ),
  };
}

beforeEach(() => {
  vi.mocked(api.economics.technicalPassports).mockResolvedValue([PASSPORT]);
  vi.mocked(api.economics.revisions).mockResolvedValue([]);
  vi.mocked(api.economics.referenceSnapshot).mockResolvedValue({
    sections: { sites: [{ code: "SITE_1", name: "Карьер №1" }] },
  } as never);
  vi.mocked(api.blockEconomics.modelDefaults).mockResolvedValue(defaultsFixture());
  vi.mocked(api.blockEconomics.runs).mockResolvedValue([]);
  vi.mocked(api.blockEconomics.variants).mockResolvedValue(variantsResponse(economicsFixture()));
});

afterEach(() => {
  cleanup();
  vi.resetAllMocks();
  // Раскрытые разделы сметы (задача 10) пишутся в sessionStorage — без
  // очистки один тест мог бы открыться уже развёрнутым состоянием соседнего.
  window.sessionStorage.clear();
});

/** Заголовок раздела «Взрывчатые материалы» в таблице сметы (не в диаграмме/легенде — там та же подпись встречается ещё трижды). */
const explosivesGroupHeading = () => screen.findByRole("button", { name: /^1\. Взрывчатые материалы/ });

/** Разворачивает все семь разделов сметы, чтобы можно было взаимодействовать со строками. */
async function expandAllGroups(user: ReturnType<typeof userEvent.setup>) {
  await explosivesGroupHeading();
  await user.click(screen.getByRole("button", { name: "Развернуть все" }));
}

describe("BlockEconomicsPage", () => {
  it("смета строится из ответа API: семь разделов и итог себестоимости", async () => {
    renderWithWorkspace(<BlockEconomicsPage passportId="PASSPORT-1" onOpenDrilling={vi.fn()} />);

    expect(await screen.findByRole("heading", { name: "Экономика блока", level: 1 })).toBeInTheDocument();
    expect(await explosivesGroupHeading()).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^7\. Постоянные и общепроизводственные расходы/ })).toBeInTheDocument();

    // `money()` разделяет тысячи неразрывным узким пробелом (U+202F) —
    // testing-library при сравнении текста узла нормализует его до обычного
    // пробела, поэтому строку для поиска нормализуем так же.
    const expectedFullCost = money(economicsFixture().markup.full_cost_rub, 0).replace(/\s/g, " ");
    expect(await screen.findByText(expectedFullCost)).toBeInTheDocument();
  });

  it("смена ВВ вызывает пересчёт и обновляет сумму строки", async () => {
    const user = userEvent.setup();
    vi.mocked(api.blockEconomics.variants)
      .mockResolvedValueOnce(variantsResponse(economicsFixture()))
      .mockResolvedValueOnce(variantsResponse(withExplosiveAmount(1500000)));

    renderWithWorkspace(<BlockEconomicsPage passportId="PASSPORT-1" onOpenDrilling={vi.fn()} />);
    await expandAllGroups(user);

    await user.click(screen.getByRole("combobox", { name: "Основное ВВ" }));
    await user.click(await screen.findByRole("option", { name: /Сферит ДТ/ }));

    await waitFor(() => expect(api.blockEconomics.variants).toHaveBeenCalledTimes(2));
    const secondCallVariants = vi.mocked(api.blockEconomics.variants).mock.calls[1][1];
    expect(secondCallVariants[0].parameters.nomenclature.EXPLOSIVE).toBe("SFERIT");

    expect(await screen.findByText("1 500 000,00")).toBeInTheDocument();
    expect(screen.getByText("Черновик · не сохранено")).toBeInTheDocument();
  });

  it("сохранение сценария создаёт прогон и снимает признак черновика", async () => {
    const user = userEvent.setup();
    const savedRun: EconomicsRun = {
      id: "RUN-1",
      organization_id: "ORG-1",
      name: "Базовый",
      technical_passport_id: "PASSPORT-1",
      package_code: "DRILL_AND_BLAST",
      reference_revision_id: "REV-1",
      parameters: {},
      result: economicsFixture(),
      created_at: "2026-01-02T00:00:00Z",
      created_by: "tester@blastex.local",
    };
    const runSummary: EconomicsRunSummary = {
      id: "RUN-1",
      name: "Базовый",
      technical_passport_id: "PASSPORT-1",
      package_code: "DRILL_AND_BLAST",
      reference_revision_id: "REV-1",
      created_at: "2026-01-02T00:00:00Z",
      created_by: "tester@blastex.local",
      price_per_m3: { full: 1500 },
    };
    vi.mocked(api.blockEconomics.saveRun).mockResolvedValue(savedRun);
    vi.mocked(api.blockEconomics.runs).mockResolvedValueOnce([]).mockResolvedValueOnce([runSummary]);

    renderWithWorkspace(<BlockEconomicsPage passportId="PASSPORT-1" onOpenDrilling={vi.fn()} />);
    await explosivesGroupHeading();

    await user.click(screen.getByRole("button", { name: "Сохранить" }));
    await user.type(screen.getByRole("textbox", { name: "Имя сценария" }), "Базовый{Enter}");

    await waitFor(() =>
      expect(api.blockEconomics.saveRun).toHaveBeenCalledWith("PASSPORT-1", expect.any(Object), "Базовый"),
    );
    expect(await screen.findByText(/Сохранён как «Базовый»/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "XLSX" })).toHaveAttribute("href", "/x/RUN-1");
  });

  it("открытие сценария из истории спрашивает подтверждение при несохранённых правках черновика", async () => {
    const user = userEvent.setup();
    const savedRun: EconomicsRun = {
      id: "RUN-1",
      organization_id: "ORG-1",
      name: "Базовый",
      technical_passport_id: "PASSPORT-1",
      package_code: "DRILL_AND_BLAST",
      reference_revision_id: "REV-1",
      parameters: {},
      result: economicsFixture(),
      created_at: "2026-01-02T00:00:00Z",
      created_by: "tester@blastex.local",
    };
    const runSummary: EconomicsRunSummary = {
      id: "RUN-1",
      name: "Базовый",
      technical_passport_id: "PASSPORT-1",
      package_code: "DRILL_AND_BLAST",
      reference_revision_id: "REV-1",
      created_at: "2026-01-02T00:00:00Z",
      created_by: "tester@blastex.local",
      price_per_m3: { full: 1500 },
    };
    vi.mocked(api.blockEconomics.runs).mockResolvedValue([runSummary]);
    vi.mocked(api.blockEconomics.run).mockResolvedValue(savedRun);
    const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(false);

    renderWithWorkspace(<BlockEconomicsPage passportId="PASSPORT-1" onOpenDrilling={vi.fn()} />);
    await explosivesGroupHeading();
    // Свежий черновик от умолчаний ещё не сохранён — savedKey пуст, поэтому «грязный» с самого начала.
    expect(screen.getByText("Черновик · не сохранено")).toBeInTheDocument();

    await user.click(screen.getByRole("tab", { name: "История" }));
    await user.click(await screen.findByRole("button", { name: "Открыть" }));

    expect(confirmSpy).toHaveBeenCalledTimes(1);
    expect(confirmSpy).toHaveBeenLastCalledWith(
      "Черновик «Вариант 1» не сохранён. Открыть другой сценарий и потерять несохранённые правки?",
    );
    // Отказ от подтверждения — прогон не запрашивается, черновик остаётся прежним.
    expect(api.blockEconomics.run).not.toHaveBeenCalled();

    confirmSpy.mockReturnValue(true);
    await user.click(screen.getByRole("button", { name: "Открыть" }));

    await waitFor(() => expect(api.blockEconomics.run).toHaveBeenCalledWith("RUN-1"));
    expect(confirmSpy).toHaveBeenCalledTimes(2);
  });

  it("открытие сценария из истории не спрашивает подтверждения, если черновик уже сохранён", async () => {
    const user = userEvent.setup();
    const savedRun: EconomicsRun = {
      id: "RUN-1",
      organization_id: "ORG-1",
      name: "Базовый",
      technical_passport_id: "PASSPORT-1",
      package_code: "DRILL_AND_BLAST",
      reference_revision_id: "REV-1",
      parameters: {},
      result: economicsFixture(),
      created_at: "2026-01-02T00:00:00Z",
      created_by: "tester@blastex.local",
    };
    const runSummary: EconomicsRunSummary = {
      id: "RUN-1",
      name: "Базовый",
      technical_passport_id: "PASSPORT-1",
      package_code: "DRILL_AND_BLAST",
      reference_revision_id: "REV-1",
      created_at: "2026-01-02T00:00:00Z",
      created_by: "tester@blastex.local",
      price_per_m3: { full: 1500 },
    };
    vi.mocked(api.blockEconomics.saveRun).mockResolvedValue(savedRun);
    vi.mocked(api.blockEconomics.runs).mockResolvedValueOnce([]).mockResolvedValueOnce([runSummary]);
    vi.mocked(api.blockEconomics.run).mockResolvedValue(savedRun);
    const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(true);

    renderWithWorkspace(<BlockEconomicsPage passportId="PASSPORT-1" onOpenDrilling={vi.fn()} />);
    await explosivesGroupHeading();

    await user.click(screen.getByRole("button", { name: "Сохранить" }));
    await user.type(screen.getByRole("textbox", { name: "Имя сценария" }), "Базовый{Enter}");
    await waitFor(() => expect(api.blockEconomics.saveRun).toHaveBeenCalled());
    // После сохранения снимок совпадает с параметрами черновика — признак «не сохранено» исчезает.
    await waitFor(() => expect(screen.queryByText("Черновик · не сохранено")).not.toBeInTheDocument());

    await user.click(screen.getByRole("tab", { name: "История" }));
    await user.click(await screen.findByRole("button", { name: "Открыть" }));

    await waitFor(() => expect(api.blockEconomics.run).toHaveBeenCalledWith("RUN-1"));
    expect(confirmSpy).not.toHaveBeenCalled();
  });

  it("ошибка пересчёта не стирает форму и прежние числа", async () => {
    const user = userEvent.setup();
    vi.mocked(api.blockEconomics.variants)
      .mockResolvedValueOnce(variantsResponse(economicsFixture()))
      .mockRejectedValueOnce(new Error("Сервис недоступен"));

    renderWithWorkspace(<BlockEconomicsPage passportId="PASSPORT-1" onOpenDrilling={vi.fn()} />);
    await expandAllGroups(user);

    await user.click(screen.getByRole("combobox", { name: "Основное ВВ" }));
    await user.click(await screen.findByRole("option", { name: /Сферит ДТ/ }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Сервис недоступен");
    expect(screen.getByRole("combobox", { name: "Основное ВВ" })).toHaveTextContent("Сферит ДТ");
    expect(screen.getByText("1 335 788,36")).toBeInTheDocument();
  });

  it("клик по сегменту диаграммы раскрывает раздел сметы", async () => {
    const user = userEvent.setup();
    renderWithWorkspace(<BlockEconomicsPage passportId="PASSPORT-1" onOpenDrilling={vi.fn()} />);
    await explosivesGroupHeading();

    const donutButtons = screen.getAllByRole("button", { name: /Взрывчатые материалы/ });
    const segment = donutButtons.find((el) => el.tagName.toLowerCase() === "path");
    expect(segment).toBeTruthy();
    await user.click(segment!);

    expect(await explosivesGroupHeading()).toHaveAttribute("aria-expanded", "true");
  });

  it("ссылка «Перейти к расчёту бурения» зовёт onOpenDrilling без лишнего пересчёта", async () => {
    const user = userEvent.setup();
    const onOpenDrilling = vi.fn();
    renderWithWorkspace(<BlockEconomicsPage passportId="PASSPORT-1" onOpenDrilling={onOpenDrilling} />);
    await expandAllGroups(user);
    await waitFor(() => expect(api.blockEconomics.variants).toHaveBeenCalledTimes(1));

    await user.click(screen.getByRole("button", { name: "Перейти к расчёту бурения (Бурение) →" }));

    expect(onOpenDrilling).toHaveBeenCalledTimes(1);
    expect(api.blockEconomics.variants).toHaveBeenCalledTimes(1);
  });

  it("раскрытые разделы сметы сохраняются в sessionStorage и восстанавливаются при новом монтировании", async () => {
    const user = userEvent.setup();
    const { unmount } = renderWithWorkspace(<BlockEconomicsPage passportId="PASSPORT-1" onOpenDrilling={vi.fn()} />);
    const heading = await explosivesGroupHeading();
    expect(heading).toHaveAttribute("aria-expanded", "false");

    await user.click(heading);
    await waitFor(() => expect(explosivesGroupHeading()).resolves.toHaveAttribute("aria-expanded", "true"));
    expect(JSON.parse(window.sessionStorage.getItem("blastex.economics.expanded") ?? "[]")).toEqual(["EXPLOSIVES"]);

    unmount();
    renderWithWorkspace(<BlockEconomicsPage passportId="PASSPORT-1" onOpenDrilling={vi.fn()} />);

    expect(await explosivesGroupHeading()).toHaveAttribute("aria-expanded", "true");
  });

  it("повреждённая запись в sessionStorage не ломает вкладку — разделы открываются свёрнутыми", async () => {
    window.sessionStorage.setItem("blastex.economics.expanded", "не json");

    renderWithWorkspace(<BlockEconomicsPage passportId="PASSPORT-1" onOpenDrilling={vi.fn()} />);

    expect(await explosivesGroupHeading()).toHaveAttribute("aria-expanded", "false");
  });

  it("вкладки «Чувствительность», «Сравнение сценариев» и «История» открываются", async () => {
    const user = userEvent.setup();
    renderWithWorkspace(<BlockEconomicsPage passportId="PASSPORT-1" onOpenDrilling={vi.fn()} />);
    await explosivesGroupHeading();

    await user.click(screen.getByRole("tab", { name: "Чувствительность" }));
    expect(screen.getByRole("button", { name: "Рассчитать ±10 %" })).toBeInTheDocument();

    await user.click(screen.getByRole("tab", { name: "Сравнение сценариев" }));
    expect(
      screen.getByText("Сохранённых сценариев ещё нет: посчитайте и нажмите «Сохранить сценарий»."),
    ).toBeInTheDocument();

    await user.click(screen.getByRole("tab", { name: "История" }));
    expect(
      screen.getByText("Сохранённых сценариев ещё нет: посчитайте и нажмите «Сохранить»."),
    ).toBeInTheDocument();
  });

  it("переключение на другой черновик сбрасывает локальный выбор подрядчика в разделе бурения", async () => {
    const user = userEvent.setup();
    const defaultsWithTwoCounterparties = {
      ...defaultsFixture(),
      counterparties: [
        { code: "CONTR_A", name: "ООО «Буровик»" },
        { code: "CONTR_B", name: "ООО «Скважина»" },
      ],
    };
    vi.mocked(api.blockEconomics.modelDefaults).mockResolvedValue(defaultsWithTwoCounterparties);
    // После дублирования вкладка запрашивает пересчёт сразу двух черновиков —
    // ответ должен нести по варианту на каждый, а не всегда один и тот же.
    vi.mocked(api.blockEconomics.variants).mockImplementation(async (_passportId, variants) => ({
      reference_revision_id: "REV-1",
      variants: variants.map((variant) => ({ name: variant.name, economics: economicsFixture() })),
    }));

    renderWithWorkspace(<BlockEconomicsPage passportId="PASSPORT-1" onOpenDrilling={vi.fn()} />);
    await expandAllGroups(user);

    // «Вариант 1» переходит на субподряд — подрядчик по умолчанию (первая
    // запись справочника, «ООО «Буровик»»), его не трогаем.
    await user.click(screen.getByRole("radio", { name: "Субподряд" }));
    expect(await screen.findByRole("combobox", { name: "Подрядчик" })).toHaveTextContent("ООО «Буровик»");

    // Дублирование создаёт «Вариант 2» с теми же параметрами и запускает
    // пересчёт обоих черновиков — дожидаемся его, иначе «Вариант 2» ещё не
    // смонтирован (вкладка показывает «Расчёт выполняется…»).
    await user.click(screen.getByRole("button", { name: "Дублировать" }));
    await waitFor(() => expect(api.blockEconomics.variants).toHaveBeenCalledTimes(2));
    await screen.findByRole("combobox", { name: "Подрядчик" });

    // На «Варианте 2» (сейчас активном) выбираем ДРУГОГО подрядчика — это
    // чисто локальный стейт `SubcontractDrillingEditor` (сбрасывает лишь
    // тариф в null, который и так null, params «Варианта 1» не трогает).
    await user.click(screen.getByRole("combobox", { name: "Подрядчик" }));
    await user.click(await screen.findByRole("option", { name: "ООО «Скважина»" }));
    expect(screen.getByRole("combobox", { name: "Подрядчик" })).toHaveTextContent("ООО «Скважина»");

    // Переключение обратно на «Вариант 1» через селектор сценария — оба
    // черновика уже посчитаны (пересчёт не перезапускается, `drafts` не
    // меняется), поэтому смета не проходит через «Расчёт выполняется…», и
    // без `key={activeId}` на `EstimateBuilder` компонент раздела бурения
    // остался бы смонтированным тем же экземпляром — с локальным выбором
    // подрядчика «Варианта 2», «протёкшим» в «Вариант 1». «Вариант 1»
    // должен показать своего подрядчика по умолчанию («ООО «Буровик»»).
    await user.selectOptions(screen.getByRole("combobox", { name: "Сценарий" }), "Вариант 1 · черновик");

    expect(await screen.findByRole("combobox", { name: "Подрядчик" })).toHaveTextContent("ООО «Буровик»");
  });
});
