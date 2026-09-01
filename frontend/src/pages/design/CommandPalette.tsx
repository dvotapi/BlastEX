import { useEffect, useMemo, useRef, useState } from "react";
import type { CameraMode3d, ViewPresetId } from "./viewPresets";
import { VIEW_PRESET_LABELS } from "./viewPresets";

export type CommandItem = {
  id: string;
  label: string;
  hint?: string;
  group: string;
  run: () => void;
};

export function buildPresetCommands(onPreset: (preset: ViewPresetId) => void): CommandItem[] {
  return (Object.keys(VIEW_PRESET_LABELS) as ViewPresetId[]).map((preset) => ({
    id: `preset-${preset}`,
    label: `Вид: ${VIEW_PRESET_LABELS[preset]}`,
    hint: preset,
    group: "Видимость",
    run: () => onPreset(preset),
  }));
}

export function buildCameraCommands(actions: {
  onFit: () => void;
  onZoomSelection: () => void;
  onToggleMeasure: () => void;
  onCameraMode3d: (mode: CameraMode3d) => void;
}): CommandItem[] {
  return [
    {
      id: "camera-fit",
      label: "Камера: показать всё",
      hint: "0",
      group: "Камера",
      run: actions.onFit,
    },
    {
      id: "camera-zoom-selection",
      label: "Камера: приблизить к выделению",
      hint: "Z",
      group: "Камера",
      run: actions.onZoomSelection,
    },
    {
      id: "camera-measure",
      label: "Инструмент: измерение",
      hint: "M",
      group: "Камера",
      run: actions.onToggleMeasure,
    },
    {
      id: "camera-3d-collar",
      label: "3D: вид с устья",
      group: "3D",
      run: () => actions.onCameraMode3d("collar"),
    },
    {
      id: "camera-3d-shaft",
      label: "3D: вид по стволу",
      group: "3D",
      run: () => actions.onCameraMode3d("shaft"),
    },
    {
      id: "camera-3d-toe",
      label: "3D: вид с забоя",
      group: "3D",
      run: () => actions.onCameraMode3d("toe"),
    },
  ];
}

export function CommandPalette({
  open,
  commands,
  onClose,
}: {
  open: boolean;
  commands: CommandItem[];
  onClose: () => void;
}) {
  const [query, setQuery] = useState("");
  const [activeIndex, setActiveIndex] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return commands;
    return commands.filter(
      (item) =>
        item.label.toLowerCase().includes(q) ||
        item.group.toLowerCase().includes(q) ||
        item.hint?.toLowerCase().includes(q),
    );
  }, [commands, query]);

  useEffect(() => {
    if (!open) return;
    setQuery("");
    setActiveIndex(0);
    inputRef.current?.focus();
  }, [open]);

  useEffect(() => {
    setActiveIndex((index) => Math.min(index, Math.max(0, filtered.length - 1)));
  }, [filtered.length]);

  useEffect(() => {
    if (!open) return;
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") {
        e.preventDefault();
        onClose();
        return;
      }
      if (e.key === "ArrowDown") {
        e.preventDefault();
        setActiveIndex((i) => Math.min(i + 1, filtered.length - 1));
        return;
      }
      if (e.key === "ArrowUp") {
        e.preventDefault();
        setActiveIndex((i) => Math.max(i - 1, 0));
        return;
      }
      if (e.key === "Enter" && filtered[activeIndex]) {
        e.preventDefault();
        filtered[activeIndex].run();
        onClose();
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [open, filtered, activeIndex, onClose]);

  if (!open) return null;

  const groups = new Map<string, CommandItem[]>();
  for (const item of filtered) {
    const list = groups.get(item.group) ?? [];
    list.push(item);
    groups.set(item.group, list);
  }

  let rowIndex = -1;

  return (
    <div className="command-palette-backdrop" onClick={onClose}>
      <div className="command-palette" role="dialog" aria-label="Командная палитра" onClick={(e) => e.stopPropagation()}>
        <input
          ref={inputRef}
          className="command-palette-input"
          placeholder="Команда… (Ctrl+K)"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          aria-label="Поиск команды"
        />
        <div className="command-palette-list">
          {filtered.length === 0 && <div className="command-palette-empty">Команды не найдены</div>}
          {Array.from(groups.entries()).map(([group, items]) => (
            <div key={group} className="command-palette-group">
              <div className="command-palette-group-title">{group}</div>
              {items.map((item) => {
                rowIndex += 1;
                const index = rowIndex;
                return (
                  <button
                    key={item.id}
                    type="button"
                    className={index === activeIndex ? "active" : ""}
                    onMouseEnter={() => setActiveIndex(index)}
                    onClick={() => {
                      item.run();
                      onClose();
                    }}
                  >
                    <span>{item.label}</span>
                    {item.hint && <kbd>{item.hint}</kbd>}
                  </button>
                );
              })}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

export function useCommandPaletteHotkey(onOpen: () => void) {
  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      const target = e.target as HTMLElement | null;
      if (target?.tagName === "INPUT" || target?.tagName === "TEXTAREA" || target?.isContentEditable) return;
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        onOpen();
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [onOpen]);
}
