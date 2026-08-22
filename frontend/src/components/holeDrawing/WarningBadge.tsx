// Маркер замечания у устья скважины. Замечания приходят с сервера
// (design/analysis.py::validate) — на чертеже они только показываются,
// собственных правил проверки здесь нет.

export function WarningBadge({
  x,
  y,
  count,
  onHover,
}: {
  x: number;
  y: number;
  count: number;
  onHover?: (hovered: boolean) => void;
}) {
  return (
    <g
      className="warning-badge"
      transform={`translate(${x} ${y})`}
      onMouseEnter={onHover ? () => onHover(true) : undefined}
      onMouseLeave={onHover ? () => onHover(false) : undefined}
    >
      <path className="warning-badge-shape" d="M0,-8 L8,6 L-8,6 Z" />
      <text className="warning-badge-mark" x="0" y="3.5" textAnchor="middle">!</text>
      {count > 1 && (
        <text className="warning-badge-count" x="11" y="6" textAnchor="start">×{count}</text>
      )}
    </g>
  );
}
