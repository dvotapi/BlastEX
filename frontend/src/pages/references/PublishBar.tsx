import { useRef } from "react";

/**
 * Нижняя панель черновика: проверка, отмена и атомарная публикация ревизии.
 * Публикация заблокирована, пока валидация возвращает ошибки.
 */
export function PublishBar({
  comment,
  onComment,
  onValidate,
  onDiscard,
  onPublish,
  onExportXlsx,
  onExportJson,
  onImport,
  canEdit,
  busy,
  dirty,
  errors,
  nextRevision,
}: {
  comment: string;
  onComment: (value: string) => void;
  onValidate: () => void;
  onDiscard: () => void;
  onPublish: () => void;
  onExportXlsx: () => void;
  onExportJson: () => void;
  onImport: (file: File) => void;
  canEdit: boolean;
  busy: boolean;
  dirty: boolean;
  errors: number;
  nextRevision: string;
}) {
  const fileInput = useRef<HTMLInputElement>(null);
  return (
    <footer className="ref-publish-bar">
      <input
        ref={fileInput}
        type="file"
        accept=".xlsx,.json"
        hidden
        onChange={(event) => {
          const file = event.target.files?.[0];
          if (file) onImport(file);
          event.target.value = "";
        }}
      />
      <button type="button" className="ref-ghost-button" onClick={onExportXlsx} disabled={busy}>
        Экспорт xlsx
      </button>
      <button type="button" className="ref-ghost-button" onClick={onExportJson} disabled={busy}>
        Экспорт JSON
      </button>
      <button
        type="button"
        className="ref-ghost-button"
        onClick={() => fileInput.current?.click()}
        disabled={!canEdit || busy}
      >
        Импорт файла
      </button>
      <input
        value={comment}
        placeholder="Комментарий к публикации"
        disabled={!canEdit || busy}
        onChange={(event) => onComment(event.target.value)}
      />
      {errors > 0 && <span className="ref-publish-errors">Ошибок: {errors}</span>}
      <button type="button" className="ref-ghost-button" onClick={onValidate} disabled={busy}>
        Проверить
      </button>
      <button type="button" className="ref-ghost-button" onClick={onDiscard} disabled={!canEdit || busy || !dirty}>
        Отменить черновик
      </button>
      <button
        type="button"
        className="primary-button"
        onClick={onPublish}
        disabled={!canEdit || busy || !dirty || errors > 0}
      >
        {nextRevision ? `Опубликовать ревизию ${nextRevision}` : "Опубликовать ревизию"}
      </button>
    </footer>
  );
}
