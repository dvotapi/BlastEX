import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api } from "../../api/endpoints";
import { CostStructure } from "./CostStructure";
import { ModelWarnings } from "./ModelWarnings";
import { ParametersPanel } from "./ParametersPanel";
import { PricePanel } from "./PricePanel";
import { RunsCompare } from "./RunsCompare";
import { SensitivityTable } from "./SensitivityTable";
import type {
  BlockEconomics,
  EconomicsRunSummary,
  ModelDefaults,
  ModelParameters,
  RunCompare,
  SensitivityRow,
  TechnicalPassport,
} from "../../types/blockEconomics";
import type { ReferenceRevision } from "../../types/economics";

const DEFAULT_PACKAGE = "DRILL_AND_BLAST";
const RECALC_DELAY_MS = 300;

// Драйверы паспорта, которые видно на вкладке: геометрия только для чтения.
const GEOMETRY_ROWS: [string, string, string][] = [
  ["rock_volume_m3", "Объём блока", "м³"],
  ["drilling_m", "Погонаж бурения", "м"],
  ["holes", "Скважины", "шт"],
  ["explosive_kg", "Масса ВВ", "кг"],
  ["downhole_nsi", "Скважинные НСИ", "шт"],
  ["surface_nsi", "Поверхностные НСИ", "шт"],
];

export function BlockEconomicsPage({ passportId }: { passportId?: string | null }) {
  const [passports, setPassports] = useState<TechnicalPassport[]>([]);
  const [selectedPassport, setSelectedPassport] = useState(passportId ?? "");
  const [packageCode, setPackageCode] = useState(DEFAULT_PACKAGE);
  const [defaults, setDefaults] = useState<ModelDefaults | null>(null);
  const [params, setParams] = useState<ModelParameters | null>(null);
  const [economics, setEconomics] = useState<BlockEconomics | null>(null);
  const [runs, setRuns] = useState<EconomicsRunSummary[]>([]);
  const [selectedRuns, setSelectedRuns] = useState<string[]>([]);
  const [compare, setCompare] = useState<RunCompare | null>(null);
  const [sensitivity, setSensitivity] = useState<SensitivityRow[]>([]);
  const [runName, setRunName] = useState("");
  const [busy, setBusy] = useState(false);
  const [sensitivityBusy, setSensitivityBusy] = useState(false);
  const [error, setError] = useState("");
  const [status, setStatus] = useState("");
  // Подписи вместо кодов: имена объектов по ревизии паспорта и номера ревизий.
  const [siteNames, setSiteNames] = useState<Record<string, Record<string, string>>>({});
  const [revisions, setRevisions] = useState<ReferenceRevision[]>([]);
  const requestId = useRef(0);
  const defaultsRequestId = useRef(0);

  useEffect(() => {
    api.economics
      .technicalPassports()
      .then((items) => {
        setPassports(items);
        setSelectedPassport((current) => current || items[0]?.id || "");
      })
      .catch((reason) =>
        setError(reason instanceof Error ? reason.message : "Не удалось загрузить паспорта."),
      );
    // Список ревизий нужен только для подписи; его отсутствие страницу не ломает.
    api.economics.revisions().then(setRevisions).catch(() => setRevisions([]));
  }, []);

  useEffect(() => {
    if (passportId) setSelectedPassport(passportId);
  }, [passportId]);

  const loadDefaults = useCallback(async () => {
    if (!selectedPassport) return;
    // Пользователь может переключить паспорт до ответа: результат устаревшего
    // запроса не должен подменить параметры уже выбранного паспорта.
    const id = ++defaultsRequestId.current;
    setBusy(true);
    setError("");
    try {
      const loaded = await api.blockEconomics.modelDefaults(selectedPassport, packageCode);
      const saved = await api.blockEconomics.runs(selectedPassport);
      if (id !== defaultsRequestId.current) return;
      setDefaults(loaded);
      setParams(loaded.parameters);
      setRuns(saved);
      setCompare(null);
      setSelectedRuns([]);
      setSensitivity([]);
    } catch (reason) {
      if (id !== defaultsRequestId.current) return;
      setError(reason instanceof Error ? reason.message : "Не удалось открыть модель.");
    } finally {
      if (id === defaultsRequestId.current) setBusy(false);
    }
  }, [selectedPassport, packageCode]);

  useEffect(() => {
    void loadDefaults();
  }, [loadDefaults]);

  // Пересчёт с задержкой: пользователь двигает параметры, а не жмёт «Рассчитать».
  useEffect(() => {
    if (!params || !selectedPassport) return;
    const id = ++requestId.current;
    const timer = window.setTimeout(() => {
      api.blockEconomics
        .compute(selectedPassport, params)
        .then((result) => {
          if (id === requestId.current) {
            setEconomics(result);
            setError("");
          }
        })
        .catch((reason) => {
          if (id === requestId.current) {
            setError(reason instanceof Error ? reason.message : "Не удалось посчитать блок.");
          }
        });
    }, RECALC_DELAY_MS);
    return () => window.clearTimeout(timer);
  }, [params, selectedPassport]);

  const passport = useMemo(
    () => defaults?.passport ?? passports.find((item) => item.id === selectedPassport) ?? null,
    [defaults, passports, selectedPassport],
  );

  // Имя объекта берётся из той ревизии, на которой создан паспорт: объект
  // могли переименовать позже, а паспорт фиксирует состояние на момент выпуска.
  const revisionId = passport?.reference_revision_id ?? "";
  useEffect(() => {
    if (!revisionId || siteNames[revisionId]) return;
    api.economics
      .referenceSnapshot(revisionId)
      .then((snapshot) => {
        const names: Record<string, string> = {};
        for (const item of snapshot.sections.sites ?? []) names[item.code] = item.name;
        setSiteNames((current) => ({ ...current, [revisionId]: names }));
      })
      .catch(() => setSiteNames((current) => ({ ...current, [revisionId]: {} })));
  }, [revisionId, siteNames]);

  const siteLabel = passport
    ? siteNames[revisionId]?.[passport.site_code] ?? passport.site_code
    : "";
  const revisionLabel = useMemo(() => {
    if (!revisionId) return "";
    const found = revisions.find((item) => item.id === revisionId);
    if (!found) return revisionId;
    const date = new Date(found.published_at).toLocaleDateString("ru-RU");
    return `Ревизия ${found.sequence_no} от ${date}`;
  }, [revisionId, revisions]);

  function patchParams(patch: Partial<ModelParameters>) {
    setParams((current) => {
      if (!current) return current;
      const next = { ...current, ...patch };
      if (patch.package_code && patch.package_code !== packageCode) setPackageCode(patch.package_code);
      return next;
    });
  }

  async function saveRun() {
    if (!params || !selectedPassport) return;
    const name = runName.trim() || `Сценарий ${runs.length + 1}`;
    setBusy(true);
    try {
      await api.blockEconomics.saveRun(selectedPassport, params, name);
      setRuns(await api.blockEconomics.runs(selectedPassport));
      setRunName("");
      setStatus(`Сценарий «${name}» сохранён.`);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Не удалось сохранить сценарий.");
    } finally {
      setBusy(false);
    }
  }

  async function computeSensitivity() {
    if (!params || !selectedPassport) return;
    setSensitivityBusy(true);
    try {
      const response = await api.blockEconomics.sensitivity(selectedPassport, params);
      setSensitivity(response.rows);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Не удалось посчитать чувствительность.");
    } finally {
      setSensitivityBusy(false);
    }
  }

  async function compareRuns() {
    if (selectedRuns.length < 2) return;
    setBusy(true);
    try {
      setCompare(await api.blockEconomics.compare(selectedRuns));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Не удалось сравнить сценарии.");
    } finally {
      setBusy(false);
    }
  }

  if (!selectedPassport) {
    return (
      <div className="page-content">
        <h2>Экономика блока</h2>
        {error && <div className="page-error">{error}</div>}
        <p className="page-caption">
          Сохранённых технических паспортов нет. Сохраните паспорт на вкладке «Расчёт БВР» —
          экономика считается по нему.
        </p>
      </div>
    );
  }

  return (
    <div className="page-content block-economics-page">
      <div className="page-heading">
        <div>
          <h2>Экономика блока</h2>
          <p>
            Две цены м³ по техническому паспорту и пакету работ: маржинальная и полная.
            Геометрия только для чтения.
          </p>
        </div>
        {status && <span className="save-status">{status}</span>}
      </div>
      {error && <div className="page-error" role="alert">{error}</div>}

      <section className="panel block-economics-passport">
        <div className="economic-fields-grid">
          <label>
            Технический паспорт
            <select value={selectedPassport} onChange={(event) => setSelectedPassport(event.target.value)}>
              {passports.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.object_name} · вер. {item.version_no}
                </option>
              ))}
            </select>
          </label>
          <label>
            Объект работ
            <input value={siteLabel} title={passport?.site_code ?? ""} disabled />
          </label>
          <label>
            Ревизия справочников паспорта
            <input value={revisionLabel} title={revisionId} disabled />
          </label>
          <label>
            Имя сценария
            <input
              value={runName}
              placeholder={`Сценарий ${runs.length + 1}`}
              onChange={(event) => setRunName(event.target.value)}
            />
          </label>
          <div className="button-row">
            <button type="button" onClick={() => void saveRun()} disabled={busy || !economics}>
              Сохранить сценарий
            </button>
          </div>
        </div>
        {passport && (
          <div className="table-scroll geometry-readonly">
            <table>
              <thead>
                <tr><th>Показатель</th><th>Значение</th><th>Ед.</th><th>Источник</th></tr>
              </thead>
              <tbody>
                {GEOMETRY_ROWS.filter(([key]) => passport.physical[key] !== undefined).map(
                  ([key, label, unit]) => (
                    <tr key={key}>
                      <td>{label}</td>
                      <td>{Number(passport.physical[key]).toLocaleString("ru-RU", { maximumFractionDigits: 2 })}</td>
                      <td>{unit}</td>
                      <td><small>{passport.lineage[key] ?? "технический расчёт"}</small></td>
                    </tr>
                  ),
                )}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <div className="block-economics-grid">
        {defaults && params && (
          <ParametersPanel params={params} defaults={defaults} onChange={patchParams} />
        )}
        <div className="block-economics-results">
          {economics ? (
            <>
              <PricePanel economics={economics} />
              <ModelWarnings economics={economics} />
              <CostStructure economics={economics} />
            </>
          ) : (
            <div className="economic-empty">Расчёт выполняется…</div>
          )}
        </div>
      </div>

      <SensitivityTable rows={sensitivity} busy={sensitivityBusy} onCompute={() => void computeSensitivity()} />

      <RunsCompare
        runs={runs}
        selected={selectedRuns}
        compare={compare}
        busy={busy}
        onToggle={(runId) =>
          setSelectedRuns((current) =>
            current.includes(runId)
              ? current.filter((item) => item !== runId)
              : current.length >= 3
                ? current
                : [...current, runId],
          )
        }
        onCompare={() => void compareRuns()}
      />
    </div>
  );
}
