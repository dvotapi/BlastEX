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
  canEdit: boolean;
  busy: boolean;
  dirty: boolean;
  errors: number;
  nextRevision: string;
}) {
  return (
    <footer className="ref-publish-bar">
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
