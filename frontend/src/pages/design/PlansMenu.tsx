// «Проекты ▾» в верхней строке «Проектирования»: сохранённые проекты блока —
// открыть, создать новый, удалить. Раньше список жил в панели «Паспорт БВР»
// вкладки «Отчёт»; панель убрана (решение владельца 12.11.2026), список — здесь.
import { useEffect, useRef, useState } from "react";
import { canDeletePlan, statusLabel } from "../../lib/lifecycle";
import type { DesignSummary } from "../../types/design";

export function PlansMenu({
  plans,
  currentDesignId,
  unsaved,
  onOpen,
  onDelete,
  onNew,
  busy,
}: {
  plans: DesignSummary[];
  currentDesignId: string;
  /** Несохранённые правки открытого проекта: открыть другой или новый — только с подтверждением. */
  unsaved: boolean;
  onOpen: (id: string) => void;
  onDelete: (id: string) => void;
  onNew: () => void;
  busy: boolean;
}) {
  const [open, setOpen] = useState(false);
  const root = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    function onPointer(event: PointerEvent) {
      if (root.current && !root.current.contains(event.target as Node)) setOpen(false);
    }
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") setOpen(false);
    }
    document.addEventListener("pointerdown", onPointer);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("pointerdown", onPointer);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  /** Сменить открытый проект: правки, которых нет на сервере, пропадут — спрашиваем. */
  function leave(action: () => void) {
    if (unsaved && !window.confirm("Есть несохранённые правки — они пропадут. Продолжить?")) return;
    setOpen(false);
    action();
  }

  return (
    <div className="plans-menu" ref={root}>
      <button type="button" className="plans-menu-toggle" aria-expanded={open} aria-haspopup="dialog" onClick={() => setOpen((value) => !value)}>
        Проекты ▾
      </button>
      {open && (
        <div className="plans-menu-popover" role="dialog" aria-label="Проекты блока">
          <button type="button" className="secondary-button" disabled={busy} onClick={() => leave(onNew)}>
            Новый проект
          </button>
          {plans.length ? (
            <ul className="plans-list">
              {plans.map((plan) => (
                <li key={plan.design_id} className={plan.design_id === currentDesignId ? "active" : ""}>
                  <button type="button" className="plans-list-open" disabled={busy} onClick={() => leave(() => onOpen(plan.design_id))}>
                    <b>{plan.name}</b>
                    <small>
                      {statusLabel(plan.lifecycle_status)} · {plan.hole_count} скв. · {new Date(plan.updated_at).toLocaleString("ru-RU")}
                    </small>
                  </button>
                  <button
                    type="button"
                    className="plans-list-delete"
                    onClick={() => {
                      if (window.confirm(`Удалить проект «${plan.name}»? Отменить удаление нельзя.`)) onDelete(plan.design_id);
                    }}
                    disabled={busy || !canDeletePlan(plan.lifecycle_status)}
                    aria-label={`Удалить «${plan.name}»`}
                  >
                    ✕
                  </button>
                </li>
              ))}
            </ul>
          ) : (
            <small className="plans-menu-empty">Сохранённых проектов нет.</small>
          )}
        </div>
      )}
    </div>
  );
}
