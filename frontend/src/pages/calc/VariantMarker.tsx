import { darken } from "../../components/holeDrawing/palette";

/** Маркер варианта заряда цветом его ВВ: в карточке варианта и в заголовках
 * таблиц сравнения. Обводка темнее заливки — светлое ВВ (Гранулит) видно на белом. */
export function VariantMarker({ color }: { color: string }) {
  return <span className="variant-marker" style={{ background: color, borderColor: darken(color, 0.35) }} aria-hidden="true" />;
}
