// Кнопки документов выпущенной ревизии паспорта на бурение (TASK-015, PR 6):
// паспорт, чертёж скважин, файл для GNSS-приёмника по профилю, ведомость и
// архив. Всё строится сервером только из снимка ревизии. DWG пока выключен —
// сервер отдаёт DXF и подсказку в заголовке, она показывается под кнопками.
import { useState } from "react";
import { downloadFile } from "../../../api/client";
import { api } from "../../../api/endpoints";
import type { DrillPassportFile, DrillPassportRevision } from "../../../types/drillPassport";

const DEFAULT_PROFILE = "PNEZD_CSV";
// Расширение файла выноса по формату профиля (`export_survey.STAKEOUT_EXTENSIONS`):
// запасное имя, если сервер имени не прислал.
const STAKEOUT_EXTENSIONS: Record<string, string> = { PNEZD_CSV: "csv", PENZD_CSV: "csv", PNEZ_TXT: "txt", DXF_POINTS: "dxf" };

const FILES: { label: string; file: DrillPassportFile }[] = [
  { label: "Паспорт PDF", file: "passport.pdf" },
  { label: "DXF", file: "holes.dxf" },
  { label: "DWG", file: "holes.dwg" },
  { label: "Ведомость PDF", file: "coords.pdf" },
  { label: "Ведомость XLSX", file: "coords.xlsx" },
  { label: "Всё архивом", file: "package.zip" },
];

export function DownloadBar({ revision }: { revision: DrillPassportRevision }) {
  // Ревизия до PR 5 профилей не хранит — файл выноса только CSV по умолчанию.
  const stakeout = revision.context.stakeout ?? { default: DEFAULT_PROFILE, profiles: { [DEFAULT_PROFILE]: { name: "CSV: точка, север, восток, отметка, описание", format: DEFAULT_PROFILE } } };
  const [profile, setProfile] = useState(stakeout.default);
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<{ text: string; error: boolean } | null>(null);

  async function download(url: string, fallback: string) {
    setBusy(true);
    setNote(null);
    try {
      const { warning } = await downloadFile(url, fallback);
      if (warning) setNote({ text: warning, error: false });
    } catch (reason) {
      setNote({ text: reason instanceof Error ? reason.message : "Не удалось скачать файл.", error: true });
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="validation-list">
      <b>Документы ревизии № {revision.revision_no}</b>
      <div className="drill-downloads">
        {FILES.map(({ label, file }) => (
          <button
            key={file}
            type="button"
            className={file === "package.zip" ? "calculate-button" : "secondary-button"}
            disabled={busy}
            onClick={() => void download(api.drillPassport.fileUrl(revision.id, file), file)}
          >
            {label}
          </button>
        ))}
      </div>
      <div className="drill-downloads">
        <label>
          Профиль приёмника
          <select value={profile} onChange={(event) => setProfile(event.target.value)} disabled={busy}>
            {Object.entries(stakeout.profiles).map(([code, item]) => (
              <option key={code} value={code}>{item.name || code}</option>
            ))}
          </select>
        </label>
        <button
          type="button"
          className="secondary-button"
          disabled={busy}
          onClick={() => {
            const extension = STAKEOUT_EXTENSIONS[stakeout.profiles[profile]?.format ?? ""] ?? "csv";
            void download(api.drillPassport.stakeoutUrl(revision.id, profile), `${profile}.${extension}`);
          }}
        >
          Файл для GNSS
        </button>
      </div>
      <small>
        Приёмник должен работать в локализации (МСК) объекта — той же, что у чертежа маркшейдера: в файле
        координаты СК объекта, самой СК в файле нет.
      </small>
      {note && <small className={note.error ? "form-error" : "frag-warnings"}>{note.text}</small>}
    </div>
  );
}
