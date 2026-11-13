// Поле справочника со списком из внешней системы (`x-options` схемы): например,
// «Позиция MagEX» материала (TASK-018 PR 7). Пользователь выбирает подпись, а не
// вводит идентификатор; список недоступен — поле только для чтения с причиной.
import { useEffect, useState } from "react";
import { api } from "../../../api/endpoints";
import type { MagexOption } from "../../../types/massBlast";
import type { FieldDescriptor } from "../schemaFields";
import { FieldShell } from "./FieldShell";

const LOADERS: Record<string, () => Promise<MagexOption[]>> = {
  "magex.materials": () => api.massBlast.magexMaterials(),
};

const UNAVAILABLE: Record<string, string> = {
  "magex.materials": "номенклатура MagEX недоступна (интеграция не включена или MagEX не отвечает)",
};

export function ExternalSelect({
  field,
  value,
  onChange,
  disabled,
  error,
}: {
  field: FieldDescriptor;
  value: string;
  onChange: (value: string) => void;
  disabled?: boolean;
  error?: string;
}) {
  const [options, setOptions] = useState<MagexOption[] | null>(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    const load = LOADERS[field.optionsSource];
    if (!load) {
      setFailed(true);
      return;
    }
    let alive = true;
    load()
      .then((items) => alive && setOptions(items))
      .catch(() => alive && setFailed(true));
    return () => {
      alive = false;
    };
  }, [field.optionsSource]);
  const known = options?.some((option) => option.value === value) ?? false;
  return (
    <FieldShell field={field} error={error} hint={failed ? `Список: ${UNAVAILABLE[field.optionsSource] ?? "недоступен"}.` : undefined}>
      <select
        id={`ref-field-${field.name}`}
        value={value}
        disabled={disabled || failed || options === null}
        onChange={(event) => onChange(event.target.value)}
      >
        <option value="">{failed ? (value ? "выбрано ранее" : "не задано") : options === null ? "загрузка…" : "не задано"}</option>
        {value && !known && !failed && options !== null && <option value={value}>выбранное ранее — нет в списке</option>}
        {(options ?? []).map((option) => (
          <option key={option.value} value={option.value}>{option.label}</option>
        ))}
      </select>
    </FieldShell>
  );
}
