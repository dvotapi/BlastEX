// @vitest-environment jsdom
import { cleanup, screen, waitFor, within } from "@testing-library/react";
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
      subcontractRateToReference: vi.fn(),
      exportUrl: (id: string) => `/x/${id}`,
    },
  },
}));

import { api } from "../../api/endpoints";
import { BlockEconomicsPage } from "./BlockEconomicsPage";
import { money } from "./format";
import { defaultsFixture, economicsFixture, paramsFixture } from "./testFixtures";
import type {
  BlockEconomics,
  EconomicsRun,
  EconomicsRunSummary,
  ModelDefaults,
  VariantsResponse,
} from "../../types/blockEconomics";

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

  it("полоса паспорта показывает ревизию паспорта, а не ревизию расчёта, даже когда они расходятся", async () => {
    // Паспорт выпущен на REV-1; справочники успели опубликовать REV-2, и
    // именно на ней посчитан текущий результат (`activeEconomics`).
    vi.mocked(api.economics.revisions).mockResolvedValue([
      { id: "REV-1", organization_id: "ORG-1", sequence_no: 1, published_at: "2026-01-01T00:00:00Z", published_by: "tester", comment: "" },
      { id: "REV-2", organization_id: "ORG-1", sequence_no: 2, published_at: "2026-02-01T00:00:00Z", published_by: "tester", comment: "" },
    ]);
    const economicsOnLaterRevision = { ...economicsFixture(), reference_revision_id: "REV-2" };
    vi.mocked(api.blockEconomics.variants).mockResolvedValue(variantsResponse(economicsOnLaterRevision));

    const { container } = renderWithWorkspace(
      <BlockEconomicsPage passportId="PASSPORT-1" onOpenDrilling={vi.fn()} />,
    );
    await screen.findByRole("heading", { name: "Экономика блока", level: 1 });

    // Блок в шапке приложения («Ревизия справочников паспорта»): ревизия ПАСПОРТА (REV-1).
    const revisionBlock = (await screen.findByText("Ревизия справочников паспорта")).parentElement;
    expect(revisionBlock).toHaveTextContent("Ревизия 1 от 01.01.2026");
    // Шапка сценариев: ревизия РАСЧЁТА (REV-2), на которой реально получен показанный результат.
    // Изначально (до ответа `variants`) шапка ещё показывает ревизию паспорта — ждём пересчёта.
    // `{context.site} · {context.passport} · {context.revision}` рендерится JSX-выражениями
    // как отдельные текстовые узлы, поэтому сравниваем `textContent` контейнера, а не `getByText`.
    await waitFor(() =>
      expect(container.querySelector(".economics-header-context")?.textContent).toBe(
        "Карьер №1 · Паспорт вер. 1 · Ревизия 2 от 01.02.2026",
      ),
    );
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

  it("прогон другого пакета работ дополняется умолчаниями своего пакета, а не открытого", async () => {
    // Пакетов в справочнике несколько (полный комплекс БВР, контурные работы
    // и другие), состав бригады и техника у них разные. Старый прогон, в
    // котором части полей нет вовсе, нельзя дополнять каталогом активного
    // пакета: в чужой сценарий попала бы чужая бригада, а перечитывание
    // каталога следом уже собранные параметры не исправляет.
    const user = userEvent.setup();
    const legacyParameters = { ...paramsFixture(), package_code: "CONTOUR_DRILL_AND_BLAST" } as unknown as Record<
      string,
      unknown
    >;
    delete legacyParameters.crew;
    const savedRun: EconomicsRun = {
      id: "RUN-CONTOUR",
      organization_id: "ORG-1",
      name: "Контурный",
      technical_passport_id: "PASSPORT-1",
      package_code: "CONTOUR_DRILL_AND_BLAST",
      reference_revision_id: "REV-1",
      parameters: legacyParameters,
      result: economicsFixture(),
      created_at: "2026-01-02T00:00:00Z",
      created_by: "tester@blastex.local",
    };
    const runSummary: EconomicsRunSummary = {
      id: "RUN-CONTOUR",
      name: "Контурный",
      technical_passport_id: "PASSPORT-1",
      package_code: "CONTOUR_DRILL_AND_BLAST",
      reference_revision_id: "REV-1",
      created_at: "2026-01-02T00:00:00Z",
      created_by: "tester@blastex.local",
      price_per_m3: { full: 1500 },
    };
    const contourCrew = [{ position_code: "POS_CONTOUR", headcount: "3", shifts_per_block: null }];
    vi.mocked(api.blockEconomics.modelDefaults).mockImplementation(async (_passport, packageCode) => ({
      ...defaultsFixture(),
      parameters: {
        ...defaultsFixture().parameters,
        package_code: packageCode,
        ...(packageCode === "CONTOUR_DRILL_AND_BLAST" ? { crew: contourCrew } : {}),
      },
    }));
    vi.mocked(api.blockEconomics.runs).mockResolvedValue([runSummary]);
    vi.mocked(api.blockEconomics.run).mockResolvedValue(savedRun);
    vi.spyOn(window, "confirm").mockReturnValue(true);

    renderWithWorkspace(<BlockEconomicsPage passportId="PASSPORT-1" onOpenDrilling={vi.fn()} />);
    await explosivesGroupHeading();

    await user.click(screen.getByRole("tab", { name: "История" }));
    await user.click(await screen.findByRole("button", { name: "Открыть" }));

    // Каталог запрошен под пакет прогона, а не под открытый.
    await waitFor(() =>
      expect(api.blockEconomics.modelDefaults).toHaveBeenCalledWith("PASSPORT-1", "CONTOUR_DRILL_AND_BLAST"),
    );
    // И именно его бригада уехала в параметры пересчёта.
    await waitFor(() => {
      const calls = vi.mocked(api.blockEconomics.variants).mock.calls;
      const last = calls[calls.length - 1][1] as Array<{ parameters: { crew: unknown } }>;
      expect(last[0].parameters.crew).toEqual(contourCrew);
    });
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

  it("смена паспорта до завершения запроса открытия прогона не подменяет черновик другого паспорта", async () => {
    const user = userEvent.setup();
    const passportB = { ...PASSPORT, id: "PASSPORT-2", object_name: "Блок №13" };
    vi.mocked(api.economics.technicalPassports).mockResolvedValue([PASSPORT, passportB]);

    const defaultsByPassport: Record<string, ModelDefaults> = {
      "PASSPORT-1": defaultsFixture(),
      "PASSPORT-2": { ...defaultsFixture(), passport: passportB },
    };
    vi.mocked(api.blockEconomics.modelDefaults).mockImplementation(async (passportId) => defaultsByPassport[passportId]);

    const runSummary: EconomicsRunSummary = {
      id: "RUN-1",
      name: "Прогон паспорта A",
      technical_passport_id: "PASSPORT-1",
      package_code: "DRILL_AND_BLAST",
      reference_revision_id: "REV-1",
      created_at: "2026-01-02T00:00:00Z",
      created_by: "tester@blastex.local",
      price_per_m3: { full: 1500 },
    };
    vi.mocked(api.blockEconomics.runs).mockImplementation(async (passportId) =>
      passportId === "PASSPORT-1" ? [runSummary] : [],
    );

    let resolveRun: (value: EconomicsRun) => void = () => {};
    const runPromise = new Promise<EconomicsRun>((resolve) => {
      resolveRun = resolve;
    });
    vi.mocked(api.blockEconomics.run).mockReturnValue(runPromise);
    // Свежий черновик от умолчаний всегда «грязный» — «Открыть» спросит
    // подтверждение потери несохранённых правок, отвечаем согласием.
    vi.spyOn(window, "confirm").mockReturnValue(true);

    renderWithWorkspace(<BlockEconomicsPage passportId="PASSPORT-1" onOpenDrilling={vi.fn()} />);
    await explosivesGroupHeading();

    await user.click(screen.getByRole("tab", { name: "История" }));
    await user.click(await screen.findByRole("button", { name: "Открыть" }));
    await waitFor(() => expect(api.blockEconomics.run).toHaveBeenCalledWith("RUN-1"));

    // Переключаемся на паспорт B до ответа сервера на открытие прогона паспорта A.
    await user.selectOptions(screen.getByRole("combobox", { name: "Технический паспорт" }), "PASSPORT-2");
    await waitFor(() => expect(api.blockEconomics.modelDefaults).toHaveBeenCalledWith("PASSPORT-2", "DRILL_AND_BLAST"));
    // Вернулись на вкладку «Смета» — `loadDefaults` паспорта B уже начал новую вкладку заново.
    await user.click(screen.getByRole("tab", { name: "Смета" }));
    await explosivesGroupHeading();

    // Запрос открытия прогона паспорта A запаздывает и завершается только теперь.
    resolveRun(
      {
        id: "RUN-1",
        organization_id: "ORG-1",
        name: "Прогон паспорта A",
        technical_passport_id: "PASSPORT-1",
        package_code: "DRILL_AND_BLAST",
        reference_revision_id: "REV-1",
        parameters: {},
        result: economicsFixture(),
        created_at: "2026-01-02T00:00:00Z",
        created_by: "tester@blastex.local",
      },
    );

    // Черновик паспорта B остаётся «Вариант 1» — устаревший ответ по паспорту A
    // не подменил его своими параметрами/именем.
    await waitFor(() =>
      expect(screen.getByRole("combobox", { name: "Сценарий" })).toHaveTextContent("Вариант 1 · черновик"),
    );
    expect(screen.queryByText("Прогон паспорта A")).not.toBeInTheDocument();
  });

  it("публикация тарифа субподряда во время переключения черновика патчит исходный черновик, а не новый активный", async () => {
    const user = userEvent.setup();
    let resolvePublish: (value: {
      section: "subcontract_rates";
      code: string;
      created: boolean;
      reference_revision_id: string;
    }) => void = () => {};
    const publishPromise = new Promise<{
      section: "subcontract_rates";
      code: string;
      created: boolean;
      reference_revision_id: string;
    }>((resolve) => {
      resolvePublish = resolve;
    });
    vi.mocked(api.blockEconomics.subcontractRateToReference).mockReturnValue(publishPromise);

    renderWithWorkspace(<BlockEconomicsPage passportId="PASSPORT-1" onOpenDrilling={vi.fn()} />);
    await expandAllGroups(user);

    // «Вариант 1» (активный на момент начала публикации) переходит на субподряд
    // и получает ручную ставку.
    await user.click(screen.getByRole("radio", { name: "Субподряд" }));
    const price = await screen.findByLabelText("Ставка субподряда, ₽/м");
    await user.clear(price);
    await user.type(price, "185");

    await user.click(screen.getByRole("button", { name: "Сохранить тариф в справочник" }));
    const nameInput = screen.getByRole("textbox", { name: "Название тарифа" });
    await user.type(nameInput, "Новый тариф");
    // Форма публикации тарифа несёт свою кнопку «Сохранить» — заголовок вкладки
    // тоже показывает кнопку с тем же именем (сохранение сценария), поэтому
    // область поиска сужена до формы публикации тарифа.
    const saveForm = nameInput.closest(".drilling-rate-save-form") as HTMLElement;
    await user.click(within(saveForm).getByRole("button", { name: "Сохранить" }));
    await waitFor(() => expect(api.blockEconomics.subcontractRateToReference).toHaveBeenCalledTimes(1));

    // Пока публикация летит на сервер, сметчик дублирует черновик — активной
    // становится новая вкладка «Вариант 2».
    await user.click(screen.getByRole("button", { name: "Дублировать" }));
    await waitFor(() =>
      expect(screen.getByRole("combobox", { name: "Сценарий" })).toHaveTextContent("Вариант 2 · черновик"),
    );
    await waitFor(() => expect(api.blockEconomics.variants).toHaveBeenCalledTimes(2));

    // Публикация тарифа завершается только теперь.
    resolvePublish({
      section: "subcontract_rates",
      code: "RATE_NEW",
      created: true,
      reference_revision_id: "REV-2",
    });

    // Патч (новый код тарифа) должен уйти в «Вариант 1» — черновик, с которого
    // публикация начиналась, — а не в «Вариант 2», ставший активным позже.
    await waitFor(() => {
      const lastCall = vi.mocked(api.blockEconomics.variants).mock.calls.at(-1);
      const variant1 = lastCall?.[1].find((item) => item.name === "Вариант 1");
      expect(variant1?.parameters.subcontract_rate_code).toBe("RATE_NEW");
    });
    const lastCall = vi.mocked(api.blockEconomics.variants).mock.calls.at(-1);
    const variant2 = lastCall?.[1].find((item) => item.name === "Вариант 2");
    expect(variant2?.parameters.subcontract_rate_code).not.toBe("RATE_NEW");
  });
});
