/**
 * Знак ComplEX — векторный, цвет берёт из `currentColor` (красный задаёт CSS).
 *
 * TODO(logo): контур временный. Исходник `ComplEX_logo.ai` в репозиторий ещё
 * не передан (он должен лечь в `Docs/design/brand/`); когда появится, сюда
 * переносится его контур без растра, `viewBox` — по контуру.
 */
export function ComplexMark({ size = 28, className }: { size?: number; className?: string }) {
  return (
    <svg
      className={`complex-mark${className ? ` ${className}` : ""}`}
      width={size}
      height={size}
      viewBox="0 0 32 32"
      role="img"
      aria-label="ComplEX"
    >
      <path d="M21.5 8.2A10 10 0 1 0 21.5 23.8" fill="none" stroke="currentColor" strokeWidth="4" strokeLinecap="round" />
      <path d="M17.5 12 26.5 20M26.5 12 17.5 20" fill="none" stroke="currentColor" strokeWidth="3.4" strokeLinecap="round" />
    </svg>
  );
}
