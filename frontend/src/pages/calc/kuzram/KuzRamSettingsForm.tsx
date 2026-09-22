import { useEffect, useId, useState } from "react";
import { ruNumber } from "../../../lib/format";
import type { KuzRamSettings, RockFactorMethod, StrengthExponent } from "../../../types";
import { Q_MIN_KG_M3, trimmed } from "./kuzramFormat";
import { KUZRAM_DEFAULTS, numericBounds, parseDecimal, sameSettings, settingError, type NumericSetting } from "./kuzramSettings";

type Option<T> = { value: T; label: string };

const METHOD_OPTIONS: Option<RockFactorMethod>[] = [
  { value: "rmd50", label: "Монолитный массив (RMD 50)" },
  { value: "rmd10", label: "Раздробленная порода (RMD 10)" },
  { value: "joint_factor", label: "По трещиноватости (JF)" },
  { value: "manual", label: "Задать вручную" },
];

const JOINT_CONDITION_OPTIONS: Option<number>[] = [
  { value: 1, label: "плотные — 1" },
  { value: 1.5, label: "раскрытые — 1,5" },
  { value: 2, label: "с заполнителем — 2" },
];

// Каннингем 2005, §4.1.1.3: «dip out of face» (40) — плоскость трещины,
// продолженная из откоса, уходит вверх, то есть трещины падают в массив.
// Формулировки — на подтверждение технологу (решение владельца 21.09.2026).
const JOINT_ANGLE_OPTIONS: Option<number>[] = [
  { value: 20, label: "падение в сторону откоса — 20" },
  { value: 30, label: "простирание поперёк откоса — 30" },
  { value: 40, label: "падение в массив — 40" },
];

const EXPONENT_OPTIONS: Option<StrengthExponent>[] = [
  { value: "19/20", label: "19/20 — Каннингем, 1987" },
  { value: "19/30", label: "19/30 — как до исправления (1983)" },
];

function SelectField<T extends string | number>({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: T;
  options: Option<T>[];
  onChange: (value: T) => void;
}) {
  const id = useId();
  return (
    <div className="kuzram-field">
      <label htmlFor={id}>{label}</label>
      <select
        id={id}
        value={String(value)}
        onChange={(event) => {
          const picked = options.find((option) => String(option.value) === event.target.value);
          if (picked) onChange(picked.value);
        }}
      >
        {options.map((option) => (
          <option key={String(option.value)} value={String(option.value)}>
            {option.label}
          </option>
        ))}
      </select>
    </div>
  );
}

/**
 * Числовая настройка. Поле хранит набранный текст: верное значение сразу уходит
 * в настройки, неверное подсвечивается и в расчёт не идёт — там остаётся
 * последнее верное.
 */
function NumberSetting({
  field,
  label,
  hint,
  value,
  onCommit,
}: {
  field: NumericSetting;
  label: string;
  hint: string;
  value: number;
  onCommit: (value: number) => void;
}) {
  const id = useId();
  const [draft, setDraft] = useState(() => trimmed(value, 6));
  // Значение сменилось снаружи (сброс, подбор C(A)) — показываем его; свой
  // незаконченный ввод («1,» при значении 1) не трогаем.
  useEffect(() => {
    setDraft((current) => (parseDecimal(current) === value ? current : trimmed(value, 6)));
  }, [value]);
  const error = settingError(field, parseDecimal(draft));
  const describedBy = [`${id}-hint`, error ? `${id}-error` : ""].filter(Boolean).join(" ");

  function change(text: string) {
    setDraft(text);
    const parsed = parseDecimal(text);
    if (parsed !== null && settingError(field, parsed) === null && parsed !== value) onCommit(parsed);
  }

  return (
    <div className="kuzram-field">
      <label htmlFor={id}>{label}</label>
      <small id={`${id}-hint`}>{hint}</small>
      <input
        id={id}
        type="text"
        inputMode="decimal"
        autoComplete="off"
        value={draft}
        aria-invalid={error ? true : undefined}
        aria-describedby={describedBy}
        onChange={(event) => change(event.target.value)}
      />
      {error && (
        <small id={`${id}-error`} className="kuzram-field-error">
          {error}
        </small>
      )}
    </div>
  );
}

/** Настройки модели Kuz-Ram. Поля JCF и JPA — только при способе JF, A — только при ручном вводе. */
export function KuzRamSettingsForm({
  settings,
  onChange,
}: {
  settings: KuzRamSettings;
  onChange: (next: KuzRamSettings) => void;
}) {
  function set<K extends keyof KuzRamSettings>(key: K, value: KuzRamSettings[K]) {
    onChange({ ...settings, [key]: value });
  }
  const method = settings.rock_factor_method;
  const manualBounds = numericBounds("rock_factor_manual");

  return (
    <fieldset className="kuzram-settings">
      <legend>Настройки модели</legend>
      <SelectField label="Фактор породы A" value={method} options={METHOD_OPTIONS} onChange={(value) => set("rock_factor_method", value)} />
      {method === "manual" && (
        <NumberSetting
          field="rock_factor_manual"
          label="A вручную"
          hint={`из опыта или отчёта, от ${trimmed(manualBounds.min)} до ${trimmed(manualBounds.max)}`}
          value={settings.rock_factor_manual}
          onCommit={(value) => set("rock_factor_manual", value)}
        />
      )}
      {method === "joint_factor" && (
        <>
          <SelectField
            label="Состояние трещин JCF"
            value={settings.joint_condition}
            options={JOINT_CONDITION_OPTIONS}
            onChange={(value) => set("joint_condition", value)}
          />
          <SelectField
            label="Ориентация трещин JPA"
            value={settings.joint_angle}
            options={JOINT_ANGLE_OPTIONS}
            onChange={(value) => set("joint_angle", value)}
          />
        </>
      )}
      <NumberSetting
        field="rock_factor_correction"
        label="Поправка C(A)"
        hint="1 — без поправки; подбирается по фактическим взрывам"
        value={settings.rock_factor_correction}
        onCommit={(value) => set("rock_factor_correction", value)}
      />
      <SelectField
        label="Показатель при силе ВВ"
        value={settings.strength_exponent}
        options={EXPONENT_OPTIONS}
        onChange={(value) => set("strength_exponent", value)}
      />
      <NumberSetting
        field="drill_deviation_m"
        label="Отклонение бурения σ, м"
        hint="стандартное отклонение забоя скважины от проекта"
        value={settings.drill_deviation_m}
        onCommit={(value) => set("drill_deviation_m", value)}
      />
      <NumberSetting
        field="uniformity_correction"
        label="Поправка C(n)"
        hint="множитель к индексу равномерности n"
        value={settings.uniformity_correction}
        onCommit={(value) => set("uniformity_correction", value)}
      />
      <NumberSetting
        field="q_max_kg_m3"
        label="Верхняя граница перебора q, кг/м³"
        hint={`перебор идёт от ${ruNumber(Q_MIN_KG_M3, 2)} с шагом 0,01`}
        value={settings.q_max_kg_m3}
        onCommit={(value) => set("q_max_kg_m3", value)}
      />
      <button
        type="button"
        className="secondary-button"
        disabled={sameSettings(settings, KUZRAM_DEFAULTS)}
        onClick={() => onChange({ ...KUZRAM_DEFAULTS })}
      >
        Сбросить к умолчаниям
      </button>
    </fieldset>
  );
}
