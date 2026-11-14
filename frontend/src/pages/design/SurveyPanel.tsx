// Панель «Съёмка бурения» (TASK-014, PR 5а): файл исполнительной съёмки,
// таблица сопоставления точек со скважинами и оценка по допускам паспорта на
// бурение, «Применить к проекту» (черновик) или «Копия по съёмке»
// (утверждённый). Состояние и запросы — в useSurveyImport, здесь только вид.
import { useRef, useState, type KeyboardEvent } from "react";
import { ruNumber } from "../../lib/format";
import type { SurveyFormat, SurveyMatchBy, SurveyMatchIssue, SurveyTolerances, SurveyVerdictCode } from "../../types/design";
import { RoleBadge } from "./RoleBadge";
import { SiteSurveyDialog } from "./SiteSurveyDialog";
import type { SurveyImportView, SurveyRow } from "./useSurveyImport";

const SURVEY_ACCEPT = ".csv,.txt,.xlsx,.xlsm,.dxf";

export const VERDICT_LABELS: Record<SurveyVerdictCode, string> = {
  ok: "ОК",
  underdrill: "ДОБУРИТЬ",
  overdrill: "ПЕРЕБУР",
  offset: "СМЕЩЕНИЕ",
  angle: "УГОЛ",
  burden: "ЛСПП",
  spacing: "ШАГ",
  no_depth: "глубина не замерена",
};

export const MATCH_BY_LABELS: Record<SurveyMatchBy, string> = {
  name: "по имени",
  nearest: "по близости",
  manual: "вручную",
  "": "",
};

export const MATCH_ISSUE_LABELS: Record<SurveyMatchIssue, string> = {
  "": "",
  unmatched_point: "точка без скважины",
  duplicate_point: "две точки",
  missing_point: "нет съёмки",
};

const FORMAT_LABELS: [SurveyFormat | "", string][] = [
  ["", "определить по файлу"],
  ["PNEZD_CSV", "CSV: точка, север, восток, отметка"],
  ["PENZD_CSV", "CSV: точка, восток, север, отметка"],
  ["PNEZ_TXT", "TXT: точка, север, восток, отметка"],
  ["DXF_POINTS", "DXF: точки и номера скважин"],
  ["TABLE", "Таблица с заголовками (CSV, XLSX)"],
];

/** Число со знаком и настоящим минусом: «+0,20», «−0,50». */
function signed(value: number | null, digits = 2): string {
  if (value === null) return "—";
  const text = ruNumber(Math.abs(value), digits);
  if (Number(text.replace(",", ".")) === 0) return text;
  return `${value < 0 ? "−" : "+"}${text}`;
}

function plain(value: number): string {
  return ruNumber(value, Number.isInteger(value) ? 0 : 1);
}

function tolerancesText(t: SurveyTolerances): string {
  const values =
    `глубина ±${ruNumber(t.depth_m)} м, устье ±${ruNumber(t.collar_m)} м, угол ±${plain(t.angle_deg)}°, ` +
    `ЛСПП ±${plain(t.burden_pct)} %, шаг ±${plain(t.spacing_pct)} %`;
  if (t.source === "default") return `Допуски: ${values} — умолчания`;
  const revision = t.revision_no !== null ? `, ревизия ${t.revision_no}` : "";
  const origin = t.source === "parent_passport" ? " прежней версии проекта" : "";
  return `Допуски: ${values} — из паспорта на бурение${origin} № ${t.passport_no || "—"}${revision}`;
}

/** Поле глубины: значение уходит в оценку по Enter или при уходе с поля. */
function DepthInput({ holeId, onCommit }: { holeId: string; onCommit: (m: number | null) => void }) {
  const [text, setText] = useState("");
  // Enter и уход с поля после него — одна оценка, а не две.
  const committed = useRef<number | null>(null);
  function commit() {
    const trimmed = text.trim();
    if (!trimmed) return;
    const value = Number(trimmed.replace(",", "."));
    if (!Number.isFinite(value) || value <= 0 || value === committed.current) return;
    committed.current = value;
    onCommit(value);
  }
  function onKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (event.key === "Enter") {
      event.preventDefault();
      commit();
    }
  }
  return (
    <input
      className="survey-depth-input"
      inputMode="decimal"
      placeholder="глубина, м"
      aria-label={`Глубина скважины ${holeId}, м`}
      value={text}
      onChange={(event) => setText(event.target.value)}
      onKeyDown={onKeyDown}
      onBlur={commit}
    />
  );
}

function statusClass(code: SurveyVerdictCode): string {
  if (code === "ok") return "ok";
  if (code === "no_depth") return "note";
  return "over";
}

function HoleCell({ row, survey }: { row: SurveyRow; survey: SurveyImportView }) {
  // Точка без скважины или спорная — инженер выбирает скважину сам.
  if (row.point && (row.issue === "unmatched_point" || row.issue === "duplicate_point")) {
    const name = row.point.name;
    return (
      <select
        aria-label={`Скважина для точки ${name}`}
        value=""
        disabled={survey.busy}
        onChange={(event) => survey.setManual(name, event.target.value)}
      >
        <option value="">{row.holeId ?? "—"}</option>
        {survey.holeIds.map((id) => (
          <option key={id} value={id}>{id}</option>
        ))}
      </select>
    );
  }
  return <span>{row.holeId ?? "—"}</span>;
}

function StatusCell({ row, survey }: { row: SurveyRow; survey: SurveyImportView }) {
  const issue = MATCH_ISSUE_LABELS[row.issue];
  const codes = row.verdict?.codes ?? [];
  return (
    <div className="survey-statuses">
      {issue && <span className="survey-status note">{issue}</span>}
      {codes.map((code) => (
        <span key={code} className={`survey-status ${statusClass(code)}`}>{VERDICT_LABELS[code]}</span>
      ))}
      {codes.includes("no_depth") && row.holeId && (
        <DepthInput holeId={row.holeId} onCommit={(m) => survey.setDepth(row.holeId as string, m)} />
      )}
      {row.point && (row.issue === "unmatched_point" || row.issue === "duplicate_point") && (
        <button
          type="button"
          className="ghost-button survey-skip"
          disabled={survey.busy}
          aria-label={`Пропустить точку ${row.point.name}`}
          onClick={() => survey.skip(row.point!.name)}
        >
          пропустить
        </button>
      )}
    </div>
  );
}

export function SurveyPanel({ survey }: { survey: SurveyImportView }) {
  const fileRef = useRef<HTMLInputElement>(null);
  const [siteOpen, setSiteOpen] = useState(false);
  const matched = survey.rows.filter((row) => row.verdict).length;
  const holesTotal = survey.holeIds.length;
  const outOfTolerance = survey.rows.filter((row) => row.verdict?.codes.some((code) => code !== "ok" && code !== "no_depth")).length;
  const copy = survey.action === "copy";

  return (
    <section className="panel survey-panel">
      <header><b>Съёмка бурения</b><RoleBadge role="executed" /></header>
      <div className="panel-body">
        <small>
          Файл исполнительной съёмки маркшейдера: точки сопоставляются со скважинами проекта и оцениваются по
          допускам паспорта на бурение. «Применить» переносит факт в проект одним шагом отмены.
        </small>
        <button type="button" className="secondary-button" disabled={survey.busy} onClick={() => fileRef.current?.click()}>
          {survey.fileName ? "Загрузить другой файл" : "Загрузить файл съёмки"}
        </button>
        <input
          ref={fileRef}
          type="file"
          accept={SURVEY_ACCEPT}
          hidden
          aria-label="Файл съёмки"
          onChange={(event) => {
            const file = event.target.files?.[0];
            event.target.value = "";
            if (file) void survey.load(file);
          }}
        />
        {survey.fileName && (
          <>
            <small>
              {survey.fileName} · точек: {survey.points.length}
            </small>
            <label>
              Формат файла
              <select
                value={survey.formatChoice}
                disabled={survey.busy}
                onChange={(event) => void survey.setFormat(event.target.value as SurveyFormat | "")}
              >
                {FORMAT_LABELS.map(([code, label]) => (
                  <option key={code} value={code}>
                    {code === "" && survey.format ? `${label} (${FORMAT_LABELS.find(([c]) => c === survey.format)?.[1] ?? ""})` : label}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Дата съёмки
              <input type="date" value={survey.surveyDate} onChange={(event) => survey.setSurveyDate(event.target.value)} />
            </label>
          </>
        )}
        {survey.swapSuggested && (
          <div className="survey-swap" role="status">
            <span>Похоже, X и Y перепутаны</span>
            <button type="button" className="secondary-button" disabled={survey.busy} onClick={() => void survey.swap()}>
              Поменять
            </button>
          </div>
        )}
        {survey.busy && <small className="survey-busy">Считаю…</small>}
        {survey.error && <small role="alert" className="frag-warnings">{survey.error}</small>}
        {survey.warnings.length > 0 && (
          <ul className="frag-warnings survey-warnings">
            {survey.warnings.map((text, index) => <li key={index}>{text}</li>)}
          </ul>
        )}
        {survey.tolerances && <small className="survey-tolerances">{tolerancesText(survey.tolerances)}</small>}
        {survey.rows.length > 0 && (
          <>
            <small>
              Со съёмкой {matched} из {holesTotal} скв.{outOfTolerance ? ` · вне допуска ${outOfTolerance}` : ""}
            </small>
            <div className="survey-table-wrap">
              <table className="survey-table">
                <thead>
                  <tr>
                    <th scope="col">Скважина</th>
                    <th scope="col">Точка</th>
                    <th scope="col">Как</th>
                    <th scope="col" title="Смещение устья в плане">Δ план, м</th>
                    <th scope="col" title="Длина по съёмке минус нужная длина">Δ глуб., м</th>
                    <th scope="col">Статус</th>
                  </tr>
                </thead>
                <tbody>
                  {survey.rows.map((row) => (
                    <tr key={row.key} className={row.issue ? "issue" : undefined}>
                      <td><HoleCell row={row} survey={survey} /></td>
                      <td>{row.point?.name ?? "—"}</td>
                      <td>{MATCH_BY_LABELS[row.by] || "—"}</td>
                      <td>{row.verdict ? ruNumber(row.verdict.offset_m) : "—"}</td>
                      <td>{row.verdict ? signed(row.verdict.depth_delta_m) : "—"}</td>
                      <td><StatusCell row={row} survey={survey} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        )}
        {survey.skipped.length > 0 && (
          <div className="survey-skipped">
            <small>Пропущены точки:</small>
            {survey.skipped.map((name) => (
              <button
                key={name}
                type="button"
                className="ghost-button"
                disabled={survey.busy}
                title="Вернуть точку в сопоставление"
                onClick={() => survey.unskip(name)}
              >
                {name} ↺
              </button>
            ))}
          </div>
        )}
        {survey.fileName && (
          <div className="plans-actions">
            <button
              type="button"
              className="calculate-button"
              disabled={survey.action === "blocked" || !survey.ready || survey.busy}
              title={survey.actionHint || undefined}
              onClick={() => void (copy ? survey.copyBySurvey() : survey.apply())}
            >
              {copy ? "Копия по съёмке" : "Применить к проекту"}
            </button>
            <button type="button" className="ghost-button" disabled={survey.busy} onClick={() => void survey.evaluate()}>
              Оценить заново
            </button>
          </div>
        )}
        {survey.fileName && survey.actionHint && <small className="frag-warnings">{survey.actionHint}</small>}
        {copy && survey.fileName && (
          <small>Проект утверждён: съёмка ляжет на его копию, копия откроется черновиком.</small>
        )}
        {survey.notice && <small role="status">{survey.notice}</small>}
        <button type="button" className="ghost-button" onClick={() => setSiteOpen(true)}>
          Съёмка старого блока
        </button>
      </div>
      {siteOpen && <SiteSurveyDialog onClose={() => setSiteOpen(false)} />}
    </section>
  );
}
