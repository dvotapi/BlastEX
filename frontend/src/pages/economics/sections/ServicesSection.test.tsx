// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ServicesSection } from "./ServicesSection";
import { buildEstimate } from "../estimateModel";
import { defaultsFixture, economicsFixture, paramsFixture } from "../testFixtures";

afterEach(cleanup);

function setup() {
  const params = paramsFixture();
  const defaults = defaultsFixture();
  const economics = economicsFixture();
  const group = buildEstimate(economics).find((g) => g.code === "SERVICES")!;
  return { params, defaults, economics, group };
}

describe("ServicesSection", () => {
  it("показывает модельную строку мобилизации, а не только ручные услуги вкладки", () => {
    const { params, defaults, economics, group } = setup();
    render(
      <ServicesSection
        group={group}
        params={params}
        defaults={defaults}
        economics={economics}
        volume={economics.block_volume_m3}
        canEdit
        onChange={() => {}}
        busyServiceName=""
        onMoveService={() => {}}
      />,
    );

    // Строка модели раздела (cost_item_code="MOBILIZATION", section="VM_LOGISTICS")
    // должна отрисоваться сама по себе — раньше `lineByCode` искал
    // несуществующий код "VM_LOGISTICS" и строка не показывалась никогда.
    expect(screen.getByText("Мобилизация и демобилизация")).toBeInTheDocument();
    expect(screen.getByText("22 000,00")).toBeInTheDocument();
  });

  it("ручная услуга с вкладки не дублируется среди строк модели", () => {
    const { params, defaults, economics, group } = setup();
    render(
      <ServicesSection
        group={group}
        params={params}
        defaults={defaults}
        economics={economics}
        volume={economics.block_volume_m3}
        canEdit
        onChange={() => {}}
        busyServiceName=""
        onMoveService={() => {}}
      />,
    );

    // "SERVICE_MANUAL_1" (quantity_origin/price_origin === "MANUAL") входит в
    // группу SERVICES по правилу `groupOf`, но должна показываться только
    // панелью ручных услуг (`ServicesPanel`, поле ввода имени), а не ещё и
    // отдельной строкой модели.
    const manualServiceLine = economicsFixture().lines.find((l) => l.cost_item_code === "SERVICE_MANUAL_1");
    expect(manualServiceLine).toBeTruthy();
    expect(screen.getAllByDisplayValue("Проживание и питание")).toHaveLength(1);
  });

  it("без строк модели (только ручная услуга) раздел не падает и показывает панель услуг", () => {
    const defaults = defaultsFixture();
    const economics = economicsFixture();
    const group = buildEstimate(economics).find((g) => g.code === "SERVICES")!;
    const onlyManual = { ...group, lines: group.lines.filter((l) => l.cost_item_code === "SERVICE_MANUAL_1") };
    render(
      <ServicesSection
        group={onlyManual}
        params={paramsFixture()}
        defaults={defaults}
        economics={economics}
        volume={economics.block_volume_m3}
        canEdit
        onChange={vi.fn()}
        busyServiceName=""
        onMoveService={() => {}}
      />,
    );

    expect(screen.queryByText("Мобилизация и демобилизация")).not.toBeInTheDocument();
    expect(screen.getByDisplayValue("Проживание и питание")).toBeInTheDocument();
  });
});
