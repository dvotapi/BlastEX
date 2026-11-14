// Выбор колонок таблицы съёмки по её заголовкам (TASK-014, PR 5а): панель
// «Съёмка бурения» и окно «Съёмка старого блока». Роли — как их понимает сервер.
import type { ReactNode } from "react";
import { HttpError } from "../../api/client";
import type { SurveyColumns, SurveyFormat } from "../../types/design";

/** Роли колонок таблицы — как их понимает сервер (`design/survey/read.py::COLUMN_KEYS`). */
const COLUMN_ROLES: [string, string][] = [
  ["name", "номер"],
  ["east", "восток"],
  ["north", "север"],
  ["z", "отметка"],
  ["depth", "глубина"],
  ["angle", "угол"],
  ["azimuth", "азимут"],
  ["wet", "вода"],
  ["water", "уровень воды"],
];

export const FORMAT_LABELS: [SurveyFormat | "", string][] = [
  ["", "определить по файлу"],
  ["PNEZD_CSV", "CSV: точка, север, восток, отметка"],
  ["PENZD_CSV", "CSV: точка, восток, север, отметка"],
  ["PNEZ_TXT", "TXT: точка, север, восток, отметка"],
  ["DXF_POINTS", "DXF: точки и номера скважин"],
  ["TABLE", "Таблица с заголовками (CSV, TXT, XLSX)"],
];

export function formatLabel(format: SurveyFormat | ""): string {
  return FORMAT_LABELS.find(([code]) => code === format)?.[1] ?? "";
}

/** Заголовки таблицы из ответа 422 чтения (колонка не найдена) — для выбора вручную. */
export function headersOf(reason: unknown): string[] {
  if (!(reason instanceof HttpError) || !reason.detail || typeof reason.detail !== "object") return [];
  const headers = (reason.detail as { headers?: unknown }).headers;
  return Array.isArray(headers) ? headers.filter((item): item is string => typeof item === "string") : [];
}

export function SurveyColumnsPicker({
  headers,
  columns,
  disabled,
  onColumn,
  children,
}: {
  headers: string[];
  columns: SurveyColumns;
  disabled: boolean;
  onColumn: (role: string, header: string) => void;
  children?: ReactNode;
}) {
  return (
    <fieldset className="survey-columns" disabled={disabled}>
      <legend>Колонки</legend>
      {COLUMN_ROLES.map(([role, label]) => (
        <label key={role}>
          {label}
          <select value={columns[role] ?? ""} onChange={(event) => onColumn(role, event.target.value)}>
            <option value="">— нет —</option>
            {headers.map((header, index) => (
              <option key={index} value={header}>{header}</option>
            ))}
          </select>
        </label>
      ))}
      {children}
    </fieldset>
  );
}
