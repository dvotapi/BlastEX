import { ComplexMark } from "./ComplexMark";

/**
 * Полный логотип для развёрнутого сайдбара: знак, слово COMPLEX с красным
 * «EX» и подложка «Комплексные решения».
 *
 * TODO(logo): знак — контур из логотипа, а слово COMPLEX и подложка набраны
 * шрифтом: их кривых в макете нет. Заменить на контуры из `ComplEX_logo.ai`,
 * когда исходник ляжет в `Docs/design/brand/`.
 */
export function ComplexLogo({ className }: { className?: string }) {
  return (
    <span className={`complex-logo${className ? ` ${className}` : ""}`} role="img" aria-label="COMPLEX — Комплексные решения">
      <ComplexMark size={40} />
      <span className="complex-logo-text" aria-hidden="true">
        <b>COMPL<em>EX</em></b>
        <small>Комплексные решения</small>
      </span>
    </span>
  );
}
