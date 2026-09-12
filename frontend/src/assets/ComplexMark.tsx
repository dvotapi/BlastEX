/**
 * Знак ComplEX — векторный контур из фирменного логотипа (перенесён из
 * согласованного макета TASK-009, доска «A · Один экран»), цвет берёт из
 * `currentColor` (красный задаёт CSS). Пропорции знака 505 × 334: `size` —
 * ширина, высота считается по ним.
 */
export function ComplexMark({ size = 28, className }: { size?: number; className?: string }) {
  return (
    <svg
      className={`complex-mark${className ? ` ${className}` : ""}`}
      width={size}
      height={Math.round((size * 334) / 505)}
      viewBox="1269 383 505 334"
      role="img"
      aria-label="ComplEX"
    >
      <path fill="currentColor" d="M 1664.9 383.3 L 1598.6 383.3 L 1560.3 427.2 L 1593.4 465.5 Z" />
      <path
        fill="currentColor"
        d="M 1460.7 547.8 L 1348.2 547.8 L 1348.2 513 L 1416.2 513 L 1416.2 465.5 L 1348.2 465.5 L 1348.2 430.7 L 1458.1 430.7 L 1509.5 490.8 C 1493.2 509.8 1477 528.8 1460.7 547.8 M 1700.7 633.9 L 1521.8 430.7 L 1522.2 430.7 L 1514.7 422.4 L 1479.5 383.3 L 1300.8 383.3 L 1300.8 465.5 L 1269.1 465.5 L 1269.1 513 L 1300.8 513 L 1300.8 595.2 L 1478.7 595.2 L 1538.7 525 L 1636.4 633.9 L 1710.6 716.6 L 1773.6 716.6 Z"
      />
    </svg>
  );
}
