import type { ReactNode } from "react";

export function StageInspector({
  title,
  onClose,
  children,
}: {
  title: string;
  onClose: () => void;
  children: ReactNode;
}) {
  return (
    <aside className="stage-inspector" aria-label={title}>
      <header>
        <b>{title}</b>
        <button type="button" className="stage-inspector-close" onClick={onClose} aria-label="Закрыть панель">×</button>
      </header>
      <div className="stage-inspector-body">
        {children}
      </div>
    </aside>
  );
}
