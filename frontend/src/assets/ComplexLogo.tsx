import { ComplexMark } from "./ComplexMark";

/**
 * Полный логотип для развёрнутого сайдбара: знак, слово COMPLEX с красным
 * «EX» и подложка «Комплексные решения».
 *
 * TODO(logo): до передачи `ComplEX_logo.ai` слово набрано шрифтом, а не
 * контуром; при замене знака заменить и надпись на кривые из исходника.
 */
export function ComplexLogo({ className }: { className?: string }) {
  return (
    <span className={`complex-logo${className ? ` ${className}` : ""}`} role="img" aria-label="COMPLEX — Комплексные решения">
      <ComplexMark size={30} />
      <span className="complex-logo-text" aria-hidden="true">
        <b>COMPL<em>EX</em></b>
        <small>Комплексные решения</small>
      </span>
    </span>
  );
}
