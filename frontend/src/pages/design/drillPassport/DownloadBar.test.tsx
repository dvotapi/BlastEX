// @vitest-environment jsdom
import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { DrillPassportRevision } from "../../../types/drillPassport";

const downloadFile = vi.hoisted(() => vi.fn());
vi.mock("../../../api/client", async (original) => ({ ...(await original<object>()), downloadFile }));

import { DownloadBar } from "./DownloadBar";

afterEach(cleanup);
beforeEach(() => {
  downloadFile.mockReset().mockResolvedValue({ filename: "f", warning: null });
});

function revision(stakeout?: DrillPassportRevision["context"]["stakeout"]): DrillPassportRevision {
  return { id: "rev-1", passport_id: "p1", revision_no: 2, content_sha256: "", created_at: "", created_by: "", context: { stakeout } };
}

const PROFILES = {
  default: "PENZD_CSV",
  profiles: {
    PNEZD_CSV: { name: "CSV: точка, север, восток, отметка, описание", format: "PNEZD_CSV" },
    PENZD_CSV: { name: "CSV: точка, восток, север, отметка, описание", format: "PENZD_CSV" },
    TRIMBLE: { name: "Trimble Access на КГОК", format: "PNEZD_CSV" },
  },
};

const BASE = "/api/v1/design/drilling-passports/revisions/rev-1";

describe("DownloadBar", () => {
  it("документы ревизии — по своим адресам", async () => {
    const user = userEvent.setup();
    render(<DownloadBar revision={revision(PROFILES)} />);
    for (const [name, file] of [
      ["Паспорт PDF", "passport.pdf"], ["DXF", "holes.dxf"], ["Ведомость PDF", "coords.pdf"],
      ["Ведомость XLSX", "coords.xlsx"], ["Всё архивом", "package.zip"],
    ]) {
      await user.click(screen.getByRole("button", { name }));
      expect(downloadFile).toHaveBeenLastCalledWith(`${BASE}/${file}`, expect.any(String));
    }
  });

  it("DWG выключен — показана подсказка сервера", async () => {
    downloadFile.mockResolvedValue({ filename: "Скважины.dxf", warning: "DWG пока не формируется: используйте DXF." });
    const user = userEvent.setup();
    render(<DownloadBar revision={revision(PROFILES)} />);
    await user.click(screen.getByRole("button", { name: "DWG" }));
    expect(downloadFile).toHaveBeenCalledWith(`${BASE}/holes.dwg`, expect.any(String));
    expect(await screen.findByText("DWG пока не формируется: используйте DXF.")).toBeTruthy();
  });

  it("профили файла выноса — из снимка ревизии, по умолчанию — профиль объекта", async () => {
    const user = userEvent.setup();
    render(<DownloadBar revision={revision(PROFILES)} />);
    const select = screen.getByLabelText("Профиль приёмника") as HTMLSelectElement;
    expect(select.value).toBe("PENZD_CSV");
    expect(within(select).getAllByRole("option").map((option) => option.textContent)).toEqual([
      "CSV: точка, север, восток, отметка, описание", "CSV: точка, восток, север, отметка, описание", "Trimble Access на КГОК",
    ]);
    await user.selectOptions(select, "TRIMBLE");
    await user.click(screen.getByRole("button", { name: "Файл для GNSS" }));
    expect(downloadFile).toHaveBeenLastCalledWith(`${BASE}/stakeout?profile=TRIMBLE`, expect.any(String));
  });

  it("ревизия до PR 5 — только PNEZD_CSV", () => {
    render(<DownloadBar revision={revision(undefined)} />);
    const select = screen.getByLabelText("Профиль приёмника") as HTMLSelectElement;
    expect(select.value).toBe("PNEZD_CSV");
    expect(within(select).getAllByRole("option")).toHaveLength(1);
  });

  it("ошибка файла выноса — текстом", async () => {
    downloadFile.mockRejectedValue(new Error("Имя точки длиннее 16 знаков: измените поле «Блок» паспорта."));
    const user = userEvent.setup();
    render(<DownloadBar revision={revision(PROFILES)} />);
    await user.click(screen.getByRole("button", { name: "Файл для GNSS" }));
    await waitFor(() => expect(screen.getByText(/Имя точки длиннее 16 знаков/)).toBeTruthy());
  });

  it("подсказка про локализацию приёмника", () => {
    render(<DownloadBar revision={revision(PROFILES)} />);
    expect(screen.getByText(/локализаци/).textContent).toContain("МСК");
  });
});
