import type { KeyboardEvent } from "react";

/** Разделы вкладки «Экономика блока» в порядке чтения слева направо. */
export type EconomicsTab = "estimate" | "structure" | "resources" | "sensitivity" | "compare" | "history";

const TABS: { id: EconomicsTab; label: string }[] = [
  { id: "estimate", label: "Смета" },
  { id: "structure", label: "Структура затрат" },
  { id: "resources", label: "Ресурсы" },
  { id: "sensitivity", label: "Чувствительность" },
  { id: "compare", label: "Сравнение сценариев" },
  { id: "history", label: "История" },
];

/**
 * Переключатель разделов страницы: смета-конструктор, структура затрат по
 * вариантам, ресурсы (натуральные величины и мощность), чувствительность,
 * сравнение сохранённых сценариев, история прогонов. Стрелки влево/вправо
 * переключают раздел по кругу, как в `VariantTabs`.
 */
export function EconomicsTabs({
  active,
  onChange,
}: {
  active: EconomicsTab;
  onChange: (tab: EconomicsTab) => void;
}) {
  function handleKeyDown(event: KeyboardEvent<HTMLButtonElement>, index: number) {
    if (event.key !== "ArrowRight" && event.key !== "ArrowLeft") return;
    event.preventDefault();
    const delta = event.key === "ArrowRight" ? 1 : -1;
    const next = TABS[(index + delta + TABS.length) % TABS.length];
    onChange(next.id);
  }

  return (
    <div className="sub-tabs economics-tabs" role="tablist" aria-label="Разделы экономики блока">
      {TABS.map((tab, index) => (
        <button
          key={tab.id}
          type="button"
          role="tab"
          aria-selected={tab.id === active}
          className={tab.id === active ? "active" : ""}
          onClick={() => onChange(tab.id)}
          onKeyDown={(event) => handleKeyDown(event, index)}
        >
          {tab.label}
        </button>
      ))}
    </div>
  );
}
