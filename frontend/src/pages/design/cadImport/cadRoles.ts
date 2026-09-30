// Цвета ролей на холсте импорта чертежа. Подписи ролей и происхождений —
// из `/design/cad/meta`, здесь только оформление.
import type { CadRolesResponse, CadSource } from "../../../types/cad";

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

/** Всплывающее пояснение бейджа происхождения роли. */
export const ORIGIN_TITLES: Record<string, string> = {
  template: "Роль из шаблона слоёв объекта — так размечен прошлый файл этого маркшейдера",
  auto: "Роль по имени слоя и типу объектов",
  z: "Верхняя или нижняя бровка по отметке относительно подошвы",
  manual: "Роль назначена вручную",
};

/** Источник после правки ролей: геометрия прежняя, роли и слои — из ответа сервера. */
export function applyRoleChanges(source: CadSource, response: CadRolesResponse): CadSource {
  return {
    ...source,
    template_saved: response.template_saved,
    floor_z_m: response.floor_z_m,
    warnings: response.warnings,
    layers: response.layers,
    entities: source.entities.map((entity) => {
      const change = response.roles[entity.handle];
      return change ? { ...entity, role: change[0], role_origin: change[1] } : entity;
    }),
  };
}
