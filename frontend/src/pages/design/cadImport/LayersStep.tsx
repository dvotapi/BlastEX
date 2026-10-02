// Шаг «Слои» импорта чертежа: слои с ролью и бейджем происхождения,
// раскрытие до отдельных объектов. Фрагменты слоя свёрнуты в одну строку —
// «Горизонт +410» из 23 кусков бровок остаётся одной строкой, пока её не раскрыть.
import { useMemo } from "react";
import { ruNumber } from "../../../lib/format";
import { plural } from "../../../lib/plural";
import type {
  CadEntity,
  CadLayer,
  CadLayerRoleCode,
  CadMeta,
  CadRoleCode,
  CadSituationKind,
  CadSource,
} from "../../../types/cad";
import { entitiesByLayer, fragmentsLabel } from "./cadGeometry";
import type { CanvasTarget } from "./CadCanvas";
import { ORIGIN_TITLES, roleColor } from "./cadRoles";

/** Сколько объектов раскрытого слоя показываем: больше — уже не выбор глазами. */
const MAX_ROWS_PER_LAYER = 200;

const LINE_KINDS = ["LWPOLYLINE", "POLYLINE2D", "POLYLINE3D", "LINE", "ARC", "CIRCLE", "ELLIPSE", "SPLINE"];
const KIND_LABELS: Record<string, string> = {
  LWPOLYLINE: "полилиния",
  POLYLINE2D: "полилиния",
  POLYLINE3D: "3D-полилиния",
  LINE: "отрезок",
  ARC: "дуга",
  CIRCLE: "окружность",
  ELLIPSE: "эллипс",
  SPLINE: "сплайн",
  POINT: "точка",
  INSERT: "знак",
  TEXT: "подпись",
  MTEXT: "подпись",
};

export type LayersStepProps = {
  source: CadSource;
  meta: CadMeta;
  hover: CanvasTarget | null;
  selected: CanvasTarget | null;
  expanded: Set<string>;
  disabled: boolean;
  onToggle: (layer: string) => void;
  onHover: (target: CanvasTarget | null) => void;
  onSelect: (target: CanvasTarget) => void;
  onLayerRole: (layer: string, role: CadLayerRoleCode) => void;
  onEntityRole: (handle: string, role: CadRoleCode | null) => void;
  /** Вид объектов ситуации слоя; null — по имени слоя (и без вида из шаблона объекта). */
  onLayerKind: (layer: string, kind: CadSituationKind | null) => void;
};

function count(kinds: Record<string, number>, names: string[]): number {
  return names.reduce((total, name) => total + (kinds[name] ?? 0), 0);
}

function zRange(min: number | null, max: number | null): string {
  if (min === null || max === null) return "";
  return `Z ${ruNumber(min, 1)}…${ruNumber(max, 1)}`;
}

function layerDetails(layer: CadLayer): string {
  const lines = count(layer.kinds, LINE_KINDS);
  const points = count(layer.kinds, ["POINT", "INSERT"]);
  const texts = count(layer.kinds, ["TEXT", "MTEXT"]);
  const parts: string[] = [];
  if (lines) parts.push(fragmentsLabel(lines));
  if (points) parts.push(`${points} ${plural(points, ["точка", "точки", "точек"])}`);
  if (texts) parts.push(`${texts} ${plural(texts, ["подпись", "подписи", "подписей"])}`);
  const range = zRange(layer.z_min, layer.z_max);
  if (range) parts.push(range);
  return parts.join(" · ");
}

function entityDetails(entity: CadEntity): string {
  if (entity.geometry_type === "text") return `«${entity.text}»`;
  if (entity.geometry_type === "point") {
    return `Z ${ruNumber(entity.points[0][2], 2)}${entity.z_from_label ? " (из подписи)" : ""}`;
  }
  const parts = [`${entity.vertex_count} т.`, `${ruNumber(entity.length_m, 1)} м`];
  if (entity.closed) parts.push(entity.closed_by_gap ? "замкнута по концам" : "замкнута");
  parts.push(zRange(entity.z_min, entity.z_max));
  return parts.join(" · ");
}

function OriginBadge({ origin, label }: { origin: string; label: string }) {
  return (
    <span className={`cad-origin cad-origin-${origin}`} title={ORIGIN_TITLES[origin]}>
      {label}
    </span>
  );
}

export function LayersStep(props: LayersStepProps) {
  const { source, meta, hover, selected, expanded, disabled } = props;
  // Таблица перерисовывается на каждое наведение — группировку считаем раз на источник.
  const byLayer = useMemo(() => entitiesByLayer(source.entities), [source.entities]);
  const roleLabel = (code: string) =>
    [...meta.roles, ...meta.layer_roles].find((item) => item.code === code)?.label ?? code;
  const originLabel = (code: string) => meta.origins.find((item) => item.code === code)?.label ?? code;
  const layerRoles = [...meta.roles, ...meta.layer_roles];

  return (
    <table className="cad-layers" aria-label="Слои чертежа">
      <thead>
        <tr>
          <th scope="col">Слой</th>
          <th scope="col">Роль</th>
          <th scope="col">
            <span className="sr-only">Происхождение роли</span>
          </th>
        </tr>
      </thead>
      <tbody>
        {source.layers.map((layer) => {
          const isOpen = expanded.has(layer.name);
          const members = byLayer.get(layer.name) ?? [];
          const visible = members.slice(0, MAX_ROWS_PER_LAYER);
          // Объект, выбранный на чертеже, показываем и за пределами первых строк.
          const picked = selected?.handle ? members.find((entity) => entity.handle === selected.handle) : undefined;
          if (picked && !visible.includes(picked)) visible.push(picked);
          const layerHovered = hover?.layer === layer.name;
          const layerSelected = selected?.layer === layer.name && selected.handle === null;
          return [
            <tr
              key={`layer:${layer.name}`}
              className={`cad-layer-row${layerHovered ? " is-hovered" : ""}${layerSelected ? " is-selected" : ""}`}
              data-layer={layer.name}
              onMouseEnter={() => props.onHover({ layer: layer.name, handle: null })}
              onMouseLeave={() => props.onHover(null)}
              onClick={(event) => {
                if ((event.target as HTMLElement).closest("select, button")) return;
                props.onSelect({ layer: layer.name, handle: null });
              }}
            >
              <td className="cad-layer-name">
                <button
                  type="button"
                  className="cad-toggle"
                  aria-expanded={isOpen}
                  aria-label={`${isOpen ? "Свернуть" : "Раскрыть"} слой ${layer.name}`}
                  onClick={() => props.onToggle(layer.name)}
                >
                  {isOpen ? "▾" : "▸"}
                </button>
                <i className="cad-swatch" style={{ background: roleColor(layer.role) }} aria-hidden="true" />
                <span>
                  <b>{layer.name}</b>
                  <small>{layerDetails(layer)}</small>
                </span>
              </td>
              <td>
                <select
                  aria-label={`Роль слоя ${layer.name}`}
                  value={layer.role}
                  disabled={disabled}
                  onChange={(event) => props.onLayerRole(layer.name, event.target.value as CadLayerRoleCode)}
                >
                  {layerRoles.map((role) => (
                    <option key={role.code} value={role.code}>
                      {role.label}
                    </option>
                  ))}
                </select>
              </td>
              <td>
                <OriginBadge origin={layer.origin} label={originLabel(layer.origin)} />
              </td>
            </tr>,
            // Вид — только у слоёв, где есть объекты ситуации: дорога, ЛЭП, склад…
            ...(layer.situation_kind
              ? [
                  <tr key={`kind:${layer.name}`} className="cad-kind-row">
                    <td className="cad-kind-label">Вид объектов</td>
                    <td>
                      <select
                        aria-label={`Вид объектов слоя ${layer.name}`}
                        value={layer.situation_kind}
                        disabled={disabled}
                        onChange={(event) =>
                          props.onLayerKind(layer.name, (event.target.value || null) as CadSituationKind | null)
                        }
                      >
                        <option value="">По имени слоя</option>
                        {meta.situation_kinds.map((kind) => (
                          <option key={kind.code} value={kind.code}>
                            {kind.label}
                          </option>
                        ))}
                      </select>
                    </td>
                    <td>
                      {layer.situation_kind_origin && (
                        <OriginBadge
                          origin={layer.situation_kind_origin}
                          label={originLabel(layer.situation_kind_origin)}
                        />
                      )}
                    </td>
                  </tr>,
                ]
              : []),
            ...(isOpen
              ? visible.map((entity) => {
                  // «Вручную» бывает и у роли, унаследованной от слоя, заданного вручную;
                  // выбранной в списке показываем только явную роль объекта.
                  const manual = entity.role_override;
                  const choices = meta.roles.filter((role) => role.applies_to.includes(entity.geometry_type));
                  return (
                    <tr
                      key={`entity:${entity.handle}`}
                      className={`cad-entity-row${hover?.handle === entity.handle ? " is-hovered" : ""}${selected?.handle === entity.handle ? " is-selected" : ""}`}
                      data-handle={entity.handle}
                      onMouseEnter={() => props.onHover({ layer: entity.layer, handle: entity.handle })}
                      onMouseLeave={() => props.onHover(null)}
                      onClick={(event) => {
                        if ((event.target as HTMLElement).closest("select, button")) return;
                        props.onSelect({ layer: entity.layer, handle: entity.handle });
                      }}
                    >
                      <td className="cad-entity-name">
                        <i className="cad-swatch" style={{ background: roleColor(entity.role) }} aria-hidden="true" />
                        <span>
                          <b>{entity.handle}</b>
                          <small>
                            {KIND_LABELS[entity.kind] ?? entity.kind} · {entityDetails(entity)}
                          </small>
                        </span>
                      </td>
                      <td>
                        <select
                          aria-label={`Роль объекта ${entity.handle}`}
                          value={manual ? entity.role : ""}
                          disabled={disabled}
                          onChange={(event) =>
                            props.onEntityRole(entity.handle, (event.target.value || null) as CadRoleCode | null)
                          }
                        >
                          <option value="">{manual ? "По слою" : `По слою: ${roleLabel(entity.role)}`}</option>
                          {choices.map((role) => (
                            <option key={role.code} value={role.code}>
                              {role.label}
                            </option>
                          ))}
                        </select>
                      </td>
                      <td>
                        <OriginBadge origin={entity.role_origin} label={originLabel(entity.role_origin)} />
                      </td>
                    </tr>
                  );
                })
              : []),
            ...(isOpen && members.length > MAX_ROWS_PER_LAYER
              ? [
                  <tr key={`more:${layer.name}`} className="cad-more-row">
                    <td colSpan={3}>
                      Показаны первые {MAX_ROWS_PER_LAYER} из {members.length}. Остальные — щелчком по линии на чертеже.
                    </td>
                  </tr>,
                ]
              : []),
          ];
        })}
      </tbody>
    </table>
  );
}
