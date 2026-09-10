import { useState } from "react";
import { MAX_VARIANTS, type Variant } from "./variants";

/**
 * Переключатель редактируемого варианта: до четырёх вкладок, имя правится
 * двойным кликом, у активного варианта — крестик закрытия (кроме последнего:
 * пустой сметы не бывает). «Дублировать» копирует активный, а не заводит
 * пустой, — так сметчик меняет одно поле и сравнивает с исходным.
 */
export function VariantTabs({
  variants,
  activeId,
  onSelect,
  onDuplicate,
  onRemove,
  onRename,
}: {
  variants: Variant[];
  activeId: string;
  onSelect: (id: string) => void;
  onDuplicate: () => void;
  onRemove: (id: string) => void;
  onRename: (id: string, name: string) => void;
}) {
  const [editingId, setEditingId] = useState("");
  const [draftName, setDraftName] = useState("");

  function startRename(variant: Variant) {
    setEditingId(variant.id);
    setDraftName(variant.name);
  }

  function commitRename() {
    const name = draftName.trim();
    if (editingId && name) onRename(editingId, name);
    setEditingId("");
  }

  return (
    <div className="sub-tabs" role="tablist">
      {variants.map((variant) => (
        <div className="variant-tab" key={variant.id}>
          {editingId === variant.id ? (
            <input
              autoFocus
              className="variant-tab-name"
              value={draftName}
              onChange={(event) => setDraftName(event.target.value)}
              onBlur={commitRename}
              onKeyDown={(event) => {
                if (event.key === "Enter") commitRename();
                if (event.key === "Escape") setEditingId("");
              }}
            />
          ) : (
            <button
              type="button"
              role="tab"
              aria-selected={variant.id === activeId}
              className={variant.id === activeId ? "active" : ""}
              onClick={() => onSelect(variant.id)}
              onDoubleClick={() => startRename(variant)}
              title="Двойной клик — переименовать"
            >
              {variant.name}
            </button>
          )}
          {variants.length > 1 && (
            <button
              type="button"
              className="variant-tab-remove"
              aria-label={`Удалить вариант «${variant.name}»`}
              onClick={() => onRemove(variant.id)}
            >
              ×
            </button>
          )}
        </div>
      ))}
      {variants.length < MAX_VARIANTS && (
        <button type="button" className="variant-tab-add" onClick={onDuplicate}>
          + Дублировать
        </button>
      )}
    </div>
  );
}
