// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { LaborSection } from "./LaborSection";
import { buildEstimate } from "../estimateModel";
import { defaultsFixture, economicsFixture, paramsFixture, payrollFixture } from "../testFixtures";
import type { BlockEconomics, BlockPayroll } from "../../../types/blockEconomics";

afterEach(cleanup);

function setup() {
  const params = paramsFixture();
  const defaults = defaultsFixture();
  const economics = economicsFixture();
  const group = buildEstimate(economics).find((g) => g.code === "LABOR")!;
  return { params, defaults, economics, group };
}

describe("LaborSection", () => {
  it("добавляет должность первой незанятой из прямых", async () => {
    const { params, defaults, economics, group } = setup();
    const onChange = vi.fn();
    const user = userEvent.setup();
    render(
      <LaborSection
        group={group}
        params={params}
        defaults={defaults}
        economics={economics}
        volume={economics.block_volume_m3}
        canEdit
        onChange={onChange}
      />,
    );

    await user.click(screen.getByRole("button", { name: "+ Добавить должность" }));

    expect(onChange).toHaveBeenCalledWith({
      crew: [...params.crew, { position_code: "MASHINIST_SZM", headcount: 1, shifts_per_block: null }],
    });
  });

  it("изменение должности вызывает onChange с новым кодом", async () => {
    const { params, defaults, economics, group } = setup();
    const onChange = vi.fn();
    const user = userEvent.setup();
    render(
      <LaborSection
        group={group}
        params={params}
        defaults={defaults}
        economics={economics}
        volume={economics.block_volume_m3}
        canEdit
        onChange={onChange}
      />,
    );

    await user.click(screen.getAllByRole("combobox", { name: "Должность" })[0]);
    await user.click(screen.getByRole("option", { name: /Взрывник/ }));

    expect(onChange).toHaveBeenCalledWith({
      crew: params.crew.map((member, i) => (i === 0 ? { ...member, position_code: "VZRYVNIK" } : member)),
    });
  });

  it("норматив становится ручным после правки численности", async () => {
    const { params, defaults, economics, group } = setup();
    const onChange = vi.fn();
    const user = userEvent.setup();
    render(
      <LaborSection
        group={group}
        params={params}
        defaults={defaults}
        economics={economics}
        volume={economics.block_volume_m3}
        canEdit
        onChange={onChange}
      />,
    );

    // Состав бригады совпадает с шаблоном пакета — обе записи стартуют с «Норматив».
    expect(screen.getAllByText("Норматив").length).toBeGreaterThan(0);

    const headcount = screen.getByLabelText("Человек в смене: Мастер БВР");
    await user.clear(headcount);
    await user.type(headcount, "2");

    expect(onChange).toHaveBeenLastCalledWith({
      crew: params.crew.map((member, i) => (i === 0 ? { ...member, headcount: "2" } : member)),
    });
  });

  it("смены на блок видны подписью, а правятся из меню строки", async () => {
    const { params, defaults, economics, group } = setup();
    const onChange = vi.fn();
    const user = userEvent.setup();
    render(
      <LaborSection
        group={group}
        params={params}
        defaults={defaults}
        economics={economics}
        volume={economics.block_volume_m3}
        canEdit
        onChange={onChange}
      />,
    );

    // Значение видно всегда — поля в строке нет, оно не наезжает на суммы.
    expect(screen.getAllByText(/Смены на блок:/).length).toBeGreaterThan(0);
    expect(screen.queryByLabelText("Смен на блок: Мастер БВР")).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Действия: Мастер БВР" }));
    await user.click(screen.getByRole("menuitem", { name: "Смены на блок" }));

    const shifts = screen.getByLabelText("Смен на блок: Мастер БВР");
    expect(shifts).toHaveFocus();
    await user.type(shifts, "3");

    expect(onChange).toHaveBeenLastCalledWith({
      crew: params.crew.map((member, i) => (i === 0 ? { ...member, shifts_per_block: "3" } : member)),
    });
  });

  it("показывает штат на ротацию экипажа техники из расчёта", () => {
    const { params, defaults, economics, group } = setup();
    const withRotation = {
      ...economics,
      natural: {
        ...economics.natural,
        values: { ...economics.natural.values, "crew_rotation.MASTER_BVR": "3" },
      },
    };
    render(
      <LaborSection
        group={group}
        params={params}
        defaults={defaults}
        economics={withRotation}
        volume={economics.block_volume_m3}
        canEdit
        onChange={vi.fn()}
      />,
    );

    expect(screen.getByText(/Штат на ротацию: 3 чел\./)).toBeInTheDocument();
    // У взрывника техники нет — и подписи нет.
    expect(screen.getAllByText(/Штат на ротацию/)).toHaveLength(1);
  });

  it("показывает «В смене» из расчёта, когда 0 в составе даёт одного человека", () => {
    const { params, defaults, economics, group } = setup();
    const zeroHeadcount = {
      ...params,
      crew: params.crew.map((member, i) => (i === 0 ? { ...member, headcount: 0 } : member)),
    };
    const withCrewPerShift = {
      ...economics,
      natural: {
        ...economics.natural,
        values: { ...economics.natural.values, "crew_per_shift.MASTER_BVR": "1" },
      },
    };
    render(
      <LaborSection
        group={group}
        params={zeroHeadcount}
        defaults={defaults}
        economics={withCrewPerShift}
        volume={economics.block_volume_m3}
        canEdit
        onChange={vi.fn()}
      />,
    );

    expect(screen.getByText(/В смене: 1 чел\./)).toBeInTheDocument();
  });

  it("не показывает «В смене», когда расчёт совпадает с составом", () => {
    const { params, defaults, economics, group } = setup();
    const withCrewPerShift = {
      ...economics,
      natural: {
        ...economics.natural,
        // У взрывника в составе уже 2 человека — расчёт подтверждает то же число.
        values: { ...economics.natural.values, "crew_per_shift.VZRYVNIK": "2" },
      },
    };
    render(
      <LaborSection
        group={group}
        params={params}
        defaults={defaults}
        economics={withCrewPerShift}
        volume={economics.block_volume_m3}
        canEdit
        onChange={vi.fn()}
      />,
    );

    expect(screen.queryByText(/В смене/)).not.toBeInTheDocument();
  });

  describe("источник ФОТ экипажа бурения", () => {
    // Должность методики совпадает с кодом из состава бригады фикстуры.
    function payrollOf(): BlockPayroll {
      const payroll = payrollFixture();
      return {
        ...payroll,
        positions: [{ ...payroll.positions[0], position_code: "MASTER_BVR", position_name: "Мастер БВР" }],
        main_position_code: "MASTER_BVR",
      };
    }

    function view(options: { source?: "RATES" | "PAYROLL"; executor?: "OWN" | "SUBCONTRACTOR"; canEdit?: boolean; economics?: BlockEconomics | null; onChange?: () => void }) {
      const base = setup();
      const economics = options.economics === undefined ? base.economics : options.economics;
      const params = { ...base.params, payroll_source: options.source ?? "RATES", drilling_executor: options.executor ?? "OWN" };
      const onChange = options.onChange ?? vi.fn();
      render(
        <LaborSection
          group={base.group}
          params={params}
          defaults={base.defaults}
          economics={economics}
          volume={base.economics.block_volume_m3}
          canEdit={options.canEdit ?? true}
          onChange={onChange}
        />,
      );
      return onChange;
    }

    it("выбор «Методика ФОТ» передаёт payroll_source", async () => {
      const onChange = vi.fn();
      view({ onChange });
      await userEvent.setup().click(screen.getByRole("radio", { name: "Методика ФОТ" }));
      expect(onChange).toHaveBeenCalledWith({ payroll_source: "PAYROLL" });
      expect(screen.getByRole("radio", { name: "Ставки" })).toBeChecked();
    });

    it("без права правки переключатель недоступен", () => {
      view({ canEdit: false });
      expect(screen.getByRole("radio", { name: "Ставки" })).toBeDisabled();
      expect(screen.getByRole("radio", { name: "Методика ФОТ" })).toBeDisabled();
    });

    it("при субподряде обе кнопки недоступны и есть подсказка", () => {
      view({ executor: "SUBCONTRACTOR" });
      expect(screen.getByRole("radio", { name: "Ставки" })).toBeDisabled();
      expect(screen.getByRole("radio", { name: "Методика ФОТ" })).toBeDisabled();
      expect(screen.getByText("Бурение на субподряде: ФОТ экипажа считает подрядчик")).toBeInTheDocument();
    });

    it("при субподряде сохранённый PAYROLL остаётся выбранным", () => {
      view({ executor: "SUBCONTRACTOR", source: "PAYROLL" });
      expect(screen.getByRole("radio", { name: "Методика ФОТ" })).toBeChecked();
      expect(screen.getByRole("radio", { name: "Методика ФОТ" })).toBeDisabled();
      expect(screen.getByRole("radio", { name: "Ставки" })).not.toBeChecked();
      expect(screen.getByRole("radio", { name: "Ставки" })).toBeDisabled();
    });

    it("в режиме ставок подсказки субподряда нет", () => {
      view({});
      expect(screen.queryByText(/Бурение на субподряде/)).not.toBeInTheDocument();
    });

    it("строка должности методики показывает c_var и разделение частей, прочие остаются", () => {
      const { economics } = setup();
      view({ source: "PAYROLL", economics: { ...economics, payroll: payrollOf() } });
      expect(screen.getByText(/Ставка: 45,00 ₽\/прив\. м/)).toBeInTheDocument();
      expect(screen.getByText(/Постоянная 90\s000 ₽ · переменная 67\s500 ₽/)).toBeInTheDocument();
      // Взрывник вне positions[] остаётся со своей подписью смен и окладом.
      expect(screen.getAllByText(/Смены на блок: норматив/)).toHaveLength(2);
      expect(screen.getByText(/ФОТ по методике: 157\s500 ₽/)).toBeInTheDocument();
    });

    it("под строками стоит разбивка методики", () => {
      const { economics } = setup();
      view({ source: "PAYROLL", economics: { ...economics, payroll: payrollOf() } });
      expect(document.querySelector(".payroll-breakdown")).not.toBeNull();
    });

    it("методика выбрана, ответ несёт причину — пояснение показано", () => {
      const { economics } = setup();
      for (const warning of [
        "Методика ФОТ не применена: нет норм бурения.",
        "ФОТ экипажа бурения посчитан по ставкам, а не по методике: ошибка",
      ]) {
        view({ source: "PAYROLL", economics: { ...economics, warnings: [warning] } });
        expect(screen.getByText("Методика не применена — причина в блоке «Модель сообщает»")).toBeInTheDocument();
        cleanup();
      }
    });

    it("ответ без причины (устаревший, после переключения), economics = null и субподряд — пояснения нет", () => {
      const { economics } = setup();
      view({ source: "PAYROLL", economics: { ...economics, warnings: ["Другое предупреждение"] } });
      expect(screen.queryByText(/Методика не применена/)).not.toBeInTheDocument();
      cleanup();
      view({ source: "PAYROLL", economics: null });
      expect(screen.queryByText(/Методика не применена/)).not.toBeInTheDocument();
      cleanup();
      view({
        source: "PAYROLL",
        executor: "SUBCONTRACTOR",
        economics: { ...economics, warnings: ["Методика ФОТ не применена: нет норм бурения."] },
      });
      expect(screen.queryByText(/Методика не применена —/)).not.toBeInTheDocument();
    });

    it("имя группы радио уникально у каждого экземпляра раздела", () => {
      const { economics } = setup();
      view({ economics });
      view({ economics });
      const names = new Set(Array.from(document.querySelectorAll<HTMLInputElement>("input[type=radio]")).map((i) => i.name));
      expect(names.size).toBe(2);
    });

    it("в режиме ставок пояснения и разбивки нет", () => {
      view({});
      expect(screen.queryByText(/Методика не применена/)).not.toBeInTheDocument();
      expect(document.querySelector(".payroll-breakdown")).toBeNull();
    });
  });
});
