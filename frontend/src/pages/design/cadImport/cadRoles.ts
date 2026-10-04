// Цвета ролей на холсте импорта чертежа. Подписи ролей и происхождений —
// из `/design/cad/meta`, здесь только оформление.
import type { CadEntity, CadRolesResponse, CadSource } from "../../../types/cad";

export const ROLE_COLORS: Record<string, string> = {
  block_contour: "#c0392b",
  design_line: "#8e44ad",
  crest_top: "#2d7556",
  crest_bottom: "#e5941c",
  feature_line: "#2f6fb0",
  contour_line: "#8a9a91",
  spot_heights: "#1f5f8b",
  situation: "#a3aca7",
  ignore: "#d7ddd9",
  crests_by_z: "#2d7556",
};

export function roleColor(role: string): string {
  return ROLE_COLORS[role] ?? ROLE_COLORS.situation;
}

// Порядок рисования линий на холсте: ситуация под бровками, контур — сверху.
// Попадание курсора выбирает из совпадающих линий ту, что сверху.
const ROLE_DRAW_ORDER = [
  "ignore",
  "situation",
  "contour_line",
  "feature_line",
  "spot_heights",
  "design_line",
  "crest_bottom",
  "crest_top",
  "block_contour",
];

/** Линии в порядке рисования (стабильно: внутри роли — порядок файла). */
export function inDrawOrder(lines: CadEntity[]): CadEntity[] {
  return [...lines].sort((a, b) => ROLE_DRAW_ORDER.indexOf(a.role) - ROLE_DRAW_ORDER.indexOf(b.role));
}

/** Всплывающее пояснение бейджа происхождения роли. */
export const ORIGIN_TITLES: Record<string, string> = {
  template: "Роль из шаблона слоёв объекта — так размечен прошлый файл этого маркшейдера",
  auto: "Роль по имени слоя и типу объектов",
  z: "Верхняя или нижняя бровка по отметке относительно подошвы",
  manual: "Роль назначена вручную",
};

/** Источник после правки ролей: геометрия прежняя, роли и слои — из ответа сервера. */
export function applyRoleChanges(source: CadSource, response: CadRolesResponse): CadSource {
  const overrides = new Set(response.overrides);
  return {
    ...source,
    template_saved: response.template_saved,
    floor_z_m: response.floor_z_m,
    warnings: response.warnings,
    layers: response.layers,
    entities: source.entities.map((entity) => {
      const change = response.roles[entity.handle];
      const override = overrides.has(entity.handle);
      if (!change && override === entity.role_override) return entity;
      return change
        ? { ...entity, role: change[0], role_origin: change[1], role_override: override }
        : { ...entity, role_override: override };
    }),
  };
}
