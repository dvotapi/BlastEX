// @vitest-environment jsdom
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("../../../api/endpoints", () => ({ api: { massBlast: { magexMaterials: vi.fn() } } }));

import { api } from "../../../api/endpoints";
import { describeField } from "../schemaFields";
import { ExternalSelect } from "./ExternalSelect";

afterEach(cleanup);

const field = describeField("magex_material_id", {
  anyOf: [{ type: "string" }, { type: "null" }], title: "Позиция MagEX", description: "Позиция номенклатуры", "x-options": "magex.materials",
});

describe("поле со списком MagEX", () => {
  it("показывает подписи позиций, а значение — идентификатор", async () => {
    const user = userEvent.setup();
    vi.mocked(api.massBlast.magexMaterials).mockResolvedValue([{ value: "m-1", label: "Сферит-ДП 1000 — ПД, шт" }]);
    const onChange = vi.fn();
    render(<ExternalSelect field={field} value="" onChange={onChange} />);
    const select = (await screen.findByLabelText("Позиция MagEX — необязательно")) as HTMLSelectElement;
    await waitFor(() => expect(select.disabled).toBe(false));
    await user.selectOptions(select, "Сферит-ДП 1000 — ПД, шт");
    expect(onChange).toHaveBeenCalledWith("m-1");
    expect(screen.queryByText(/m-1/)).toBeNull();
  });

  it("без MagEX — только чтение с причиной", async () => {
    vi.mocked(api.massBlast.magexMaterials).mockRejectedValue(new Error("404"));
    render(<ExternalSelect field={field} value="m-1" onChange={vi.fn()} />);
    expect(await screen.findByText(/номенклатура MagEX недоступна/)).toBeTruthy();
    expect((screen.getByLabelText("Позиция MagEX — необязательно") as HTMLSelectElement).disabled).toBe(true);
  });
});
