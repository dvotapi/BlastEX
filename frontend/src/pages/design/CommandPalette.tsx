import { useEffect, useMemo, useRef, useState } from "react";
import {
  CAMERA_MODE_LABELS,
  VIEW_PRESET_LABELS,
  type CameraMode3d,
  type ViewPresetId,
} from "./viewPresets";

export type DesignCommand = {
  id: string;
  label: string;
  keywords: string[];
  run: () => void;
};

export function CommandPalette({
  open,
  commands,
  onClose,
}: {
  open: boolean;
  commands: DesignCommand[];
  onClose: () => void;
}) {
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!open) {
      setQuery("");
      setActive(0);
      return;
    }
    inputRef.current?.focus();
  }, [open]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return commands;
    return commands.filter((cmd) =>
      cmd.label.toLowerCase().includes(q)
      || cmd.keywords.some((k) => k.includes(q)),
    );
  }, [commands, query]);

  useEffect(() => {
    setActive(0);
  }, [query]);

  useEffect(() => {
    if (!open) return undefined;
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") {
        e.preventDefault();
        onClose();
      }
      if (e.key === "ArrowDown") {
        e.preventDefault();
        setActive((i) => Math.min(i + 1, Math.max(0, filtered.length - 1)));
      }
      if (e.key === "ArrowUp") {
        e.preventDefault();
        setActive((i) => Math.max(i - 1, 0));
      }
      if (e.key === "Enter" && filtered[active]) {
        e.preventDefault();
        filtered[active].run();
        onClose();
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, filtered, active, onClose]);

  if (!open) return null;

  return (
    <div className="command-palette-backdrop" onClick={onClose} role="presentation">
      <div className="command-palette" role="dialog" aria-label="Поиск команд" onClick={(e) => e.stopPropagation()}>
        <input
          ref={inputRef}
          type="search"
          placeholder="Команда… (изолинии, линейка, устье)"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          aria-label="Поиск команды"
        />
        <ul role="listbox">
          {filtered.length === 0 && <li className="empty">Ничего не найдено</li>}
          {filtered.map((cmd, index) => (
            <li key={cmd.id}>
              <button
                type="button"
                role="option"
                aria-selected={index === active}
                className={index === active ? "active" : ""}
                onMouseEnter={() => setActive(index)}
                onClick={() => {
                  cmd.run();
                  onClose();
                }}
              >
                {cmd.label}
              </button>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}

export function buildPresetCommands(onPreset: (preset: ViewPresetId) => void): DesignCommand[] {
  return (Object.keys(VIEW_PRESET_LABELS) as ViewPresetId[]).map((preset) => ({
    id: `preset-${preset}`,
    label: `Пресет: ${VIEW_PRESET_LABELS[preset]}`,
    keywords: [VIEW_PRESET_LABELS[preset].toLowerCase(), preset],
    run: () => onPreset(preset),
  }));
}

// Разговорные формы из привычки инженера: «только устья», «вид подошвы».
const CAMERA_MODE_SYNONYMS: Record<CameraMode3d, string[]> = {
  collar: ["только устья", "только устье", "устья", "оголовки"],
  shaft: ["только стволы", "стволы", "весь ствол"],
  toe: ["только подошва", "вид подошвы", "подошвы", "забой"],
};

export function buildCameraCommands(onCamera: (mode: CameraMode3d) => void): DesignCommand[] {
  return (Object.keys(CAMERA_MODE_LABELS) as CameraMode3d[]).map((mode) => ({
    id: `camera-${mode}`,
    label: `3D: ${CAMERA_MODE_LABELS[mode]}`,
    keywords: [CAMERA_MODE_LABELS[mode].toLowerCase(), "3d", mode, ...CAMERA_MODE_SYNONYMS[mode]],
    run: () => onCamera(mode),
  }));
}
