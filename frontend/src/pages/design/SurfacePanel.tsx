import { useRef, useState, type ReactNode } from "react";
import { ruNumber } from "../../lib/format";
import type { BenchSurface, CoordinateSystem, SurfaceKind, SurfaceModel, SurfaceSet } from "../../types/design";
import { RoleBadge } from "./RoleBadge";
import { isCrsUnconfirmed } from "./workflowStatus";

const KIND_OPTIONS: { value: SurfaceKind; label: string }[] = [
  { value: "top", label: "Кровля" },
  { value: "floor", label: "Подошва" },
  { value: "face", label: "Откос" },
  { value: "post_blast", label: "После взрыва" },
];

const KIND_HINT: Record<SurfaceKind, string> = {
  top: "Устья скважин лягут на эту поверхность",
  floor: "Глубина считается до подошвы + перебур",
  face: "Откос для 3D и разреза",
  post_blast: "Хранится отдельно, не подменяет проект",
};

function Section({
  title,
  defaultOpen,
  children,
}: {
  title: string;
  defaultOpen: boolean;
  children: ReactNode;
}) {
  return (
    <details className="survey-section" open={defaultOpen}>
      <summary>{title}</summary>
      <div className="survey-section-body">{children}</div>
    </details>
  );
}

export function SurfacePanel({
  surfaces,
  bench,
  coordinateSystem,
  onBenchChange,
  onCoordinateSystemChange,
  onImport,
  onImportBlock,
  onClear,
  busy,
}: {
  surfaces: SurfaceSet;
  bench: BenchSurface;
  coordinateSystem: CoordinateSystem;
  onBenchChange: (patch: Partial<BenchSurface>) => void;
  onCoordinateSystemChange: (patch: Partial<CoordinateSystem>) => void;
  onImport: (kind: SurfaceKind, file: File) => void;
  onImportBlock: (file: File) => void;
  onClear: (kind: SurfaceKind) => void;
  busy: boolean;
}) {
  const [kind, setKind] = useState<SurfaceKind>("top");
  const inputRef = useRef<HTMLInputElement>(null);
  const blockInputRef = useRef<HTMLInputElement>(null);
  const hasSurfaces = Boolean(surfaces.top || surfaces.floor || surfaces.face);
  const crsWarning = isCrsUnconfirmed(coordinateSystem, hasSurfaces);

  function onFile(file: File | undefined) {
    if (!file) return;
    onImport(kind, file);
    if (inputRef.current) inputRef.current.value = "";
  }

  function pickDxf() {
    blockInputRef.current?.click();
  }

  return (
    <section className="panel">
      <header><b>Съёмка уступа</b><RoleBadge role="designed" /></header>
      <div className="panel-body">
        <div className="dxf-block-import primary-import">
          <b>Импортировать 3D‑каркас DXF</b>
          <small>Слои «верхняя бровка» и «нижняя бровка» создадут контур, кровлю, подошву и откос. Существующие скважины будут очищены.</small>
          <button type="button" className="primary-button" disabled={busy} onClick={pickDxf}>
            {busy ? "Импортирую…" : "Импортировать 3D‑каркас DXF"}
          </button>
          <input
            ref={blockInputRef}
            type="file"
            accept=".dxf"
            hidden
            disabled={busy}
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (file) onImportBlock(file);
              if (blockInputRef.current) blockInputRef.current.value = "";
            }}
          />
        </div>

        <Section title="Координаты" defaultOpen={crsWarning || !hasSurfaces}>
          {crsWarning && (
            <div className="crs-banner" role="status">
              Система координат не подтверждена. Импортированы реальные координаты, но EPSG не задан.
            </div>
          )}
          <label>
            Система координат
            <input
              value={coordinateSystem.name}
              onChange={(e) => onCoordinateSystemChange({ name: e.target.value })}
              placeholder="local / mine grid"
            />
          </label>
          <label>
            EPSG
            <input
              type="number"
              value={coordinateSystem.epsg ?? ""}
              onChange={(e) => {
                const epsg = e.target.value === "" ? null : Number(e.target.value);
                onCoordinateSystemChange({ epsg, confirmed: epsg != null });
              }}
              placeholder="не задан"
            />
          </label>
          {crsWarning && (
            <button
              type="button"
              className="secondary-button"
              onClick={() => onCoordinateSystemChange({ confirmed: true })}
            >
              Подтвердить СК
            </button>
          )}
        </Section>

        <Section title="Бровки" defaultOpen={!hasSurfaces}>
          <div className="field-pair">
            <label>
              Бровка (плоскость), м
              <input type="number" step="0.1" value={bench.crest_z_m} onChange={(e) => onBenchChange({ crest_z_m: Number(e.target.value) })} />
            </label>
            <label>
              Подошва (плоскость), м
              <input type="number" step="0.1" value={bench.toe_z_m} onChange={(e) => onBenchChange({ toe_z_m: Number(e.target.value) })} />
            </label>
          </div>
          <small>Плоскость используется, если съёмка не покрывает точку.</small>
        </Section>

        <Section title="Импорт" defaultOpen={false}>
          <label>
            Тип поверхности
            <select value={kind} onChange={(e) => setKind(e.target.value as SurfaceKind)}>
              {KIND_OPTIONS.map((opt) => <option key={opt.value} value={opt.value}>{opt.label}</option>)}
            </select>
          </label>
          <small>{KIND_HINT[kind]}</small>
          <input
            ref={inputRef}
            type="file"
            accept=".xyz,.txt,.csv,.dxf,.geojson,.json"
            disabled={busy}
            onChange={(e) => onFile(e.target.files?.[0])}
          />
          <small>XYZ, CSV, DXF (точки и полилинии), GeoJSON</small>
        </Section>

        <Section title="Поверхности" defaultOpen={hasSurfaces}>
          <div className="surface-list">
            {KIND_OPTIONS.map((opt) => (
              <SurfaceCard
                key={opt.value}
                label={opt.label}
                surface={surfaces[opt.value]}
                onClear={() => onClear(opt.value)}
                busy={busy}
              />
            ))}
          </div>
        </Section>
      </div>
    </section>
  );
}

function SurfaceCard({
  label,
  surface,
  onClear,
  busy,
}: {
  label: string;
  surface: SurfaceModel | null;
  onClear: () => void;
  busy: boolean;
}) {
  if (!surface) {
    return (
      <div className="surface-card empty">
        <b>{label}</b>
        <small>плоскость уступа</small>
      </div>
    );
  }
  const zMin = surface.tin.vertices.length ? Math.min(...surface.tin.vertices.map((v) => v.z)) : null;
  const zMax = surface.tin.vertices.length ? Math.max(...surface.tin.vertices.map((v) => v.z)) : null;
  return (
    <div className="surface-card">
      <div>
        <b>{label}</b>
        <small>
          {surface.source_name || surface.source_format || "съёмка"} · {surface.tin.vertices.length} т. · {surface.tin.triangles.length} тр.
          {zMin !== null && zMax !== null ? ` · Z ${ruNumber(zMin, 1)}…${ruNumber(zMax, 1)}` : ""}
        </small>
      </div>
      <button type="button" className="secondary-button" onClick={onClear} disabled={busy}>Снять</button>
    </div>
  );
}
