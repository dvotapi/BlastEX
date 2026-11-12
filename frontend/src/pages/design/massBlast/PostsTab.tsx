// Вкладка «Посты и план»: посты охраны (п. 35 распорядка) и точки на
// ситуационном плане Г.5 — постов, взрывной станции, укрытия, места сбора.
import { useState } from "react";
import { api } from "../../../api/endpoints";
import type { LayoutPointKind } from "../../../types/massBlast";
import { issuesFor, numberText, POINT_KINDS } from "./form";
import { LayoutPlan } from "./LayoutPlan";
import type { TabProps } from "./ProjectTabs";
import { errorText, Field, Issues, ruNum, TextInput } from "./ui";

const KIND_LABEL = Object.fromEntries(POINT_KINDS.map((item) => [item.code, item.label])) as Record<LayoutPointKind, string>;

export function PostsTab({ form, edit, editable, errors, issues, context, projectId, ensureSaved }: TabProps & {
  projectId: string;
  /** Несохранённые правки (например, ручная зона) сначала сохраняются: посты — по текущим зонам. */
  ensureSaved: () => Promise<unknown>;
}) {
  const [suggesting, setSuggesting] = useState(false);
  const [note, setNote] = useState<{ text: string; error: boolean } | null>(null);

  /** «Предложить посты» (В6): посты на пересечениях дорог с границей зоны, станция и укрытие за зоной. */
  async function suggest() {
    setSuggesting(true);
    setNote(null);
    try {
      if (!(await ensureSaved())) return;
      const result = await api.massBlast.suggestLayout(projectId);
      // Нет пересечений дорог с границей зоны — постов нет: существующие не трогаем.
      if (!result.posts.length) {
        setNote({ text: result.reason || "Предложить нечего.", error: false });
        return;
      }
      const replacing = form.guard_posts.length > 0 || form.points.some((point) => point.kind !== "gather");
      if (replacing && !window.confirm("Заменить посты, взрывную станцию и укрытие предложенными? Место сбора останется.")) return;
      edit((draft) => {
        draft.guard_posts = result.posts.map((post) => ({ code: post.code, location: post.location, responsible_employee_code: "", notes: "" }));
        draft.points = [
          ...draft.points.filter((point) => point.kind === "gather"),
          ...result.points.map((point) => ({ ...point, x: String(point.x).replace(".", ","), y: String(point.y).replace(".", ",") })),
        ];
      });
      setNote({
        text: `Предложено постов: ${result.posts.length}. Проверьте места на плане и сохраните проект.${result.reason ? ` ${result.reason}` : ""}`,
        error: false,
      });
    } catch (reason) {
      setNote({ text: errorText(reason, "Не удалось предложить посты."), error: true });
    } finally {
      setSuggesting(false);
    }
  }

  const disabled = !editable;
  const [kind, setKind] = useState<LayoutPointKind>("guard_post");
  const posts = form.guard_posts.map((post) => post.code.trim()).filter(Boolean);
  const [postRef, setPostRef] = useState(posts[0] ?? "");
  const ref = posts.includes(postRef) ? postRef : posts[0] ?? "";
  const graphics = context?.graphics;
  // Расстояние до блока — у сохранённых точек (сервер); у сдвинутых без сохранения — после проверки.
  const distances = new Map((graphics?.points ?? []).map((point) => [`${point.kind}:${point.ref}:${point.x}:${point.y}`, point.distance_m]));

  function place(pointKind: LayoutPointKind, pointRef: string, x: number, y: number) {
    if (pointKind === "guard_post" && !pointRef) return;
    edit((draft) => {
      const at = draft.points.findIndex((point) => point.kind === pointKind && point.ref === pointRef);
      const next = { kind: pointKind, ref: pointRef, x: numberText(x), y: numberText(y), label: at >= 0 ? draft.points[at].label : "" };
      if (at >= 0) draft.points[at] = next;
      else draft.points.push(next);
    });
  }

  return (
    <>
      <fieldset>
        <legend>Посты охраны опасной зоны</legend>
        {form.guard_posts.map((post, index) => (
          <div key={index} className="drill-grid drill-post">
            <TextInput label="Пост №" value={post.code} disabled={disabled} maxLength={80} error={errors[`guard_posts[${index}].code`]}
              onChange={(value) => edit((draft) => {
                const old = draft.guard_posts[index].code;
                draft.guard_posts[index].code = value;
                // Точка поста идёт за его номером.
                draft.points.forEach((point) => { if (point.kind === "guard_post" && point.ref === old) point.ref = value; });
              })} />
            <TextInput label="Место поста" value={post.location} disabled={disabled} maxLength={500} error={errors[`guard_posts[${index}].location`]}
              onChange={(value) => edit((draft) => { draft.guard_posts[index].location = value; })} />
            <TextInput label="Охраняет (Ф. И. О.)" value={post.responsible_employee_code} disabled={disabled} maxLength={80}
              onChange={(value) => edit((draft) => { draft.guard_posts[index].responsible_employee_code = value; })} />
            <TextInput label="Примечание" value={post.notes} disabled={disabled} maxLength={1000}
              onChange={(value) => edit((draft) => { draft.guard_posts[index].notes = value; })} />
            {editable && (
              <button type="button" className="link-button" onClick={() => edit((draft) => {
                const [removed] = draft.guard_posts.splice(index, 1);
                draft.points = draft.points.filter((point) => !(point.kind === "guard_post" && point.ref === removed.code));
              })}>
                Удалить пост
              </button>
            )}
          </div>
        ))}
        {errors.guard_posts && <small className="form-error">{errors.guard_posts}</small>}
        {editable && context?.graphics?.has_situation && (
          <button type="button" className="secondary-button" disabled={suggesting} onClick={() => void suggest()}
            title="Посты — где дороги пересекают границу зоны для людей, станция и укрытие — за зоной">
            Предложить посты
          </button>
        )}
        {note && <small className={note.error ? "form-error" : "drill-message"}>{note.text}</small>}
        {editable && (
          <button type="button" className="secondary-button" onClick={() => edit((draft) => {
            const used = new Set(draft.guard_posts.map((post) => post.code));
            let number = draft.guard_posts.length + 1;
            while (used.has(String(number))) number += 1;
            draft.guard_posts.push({ code: String(number), location: "", responsible_employee_code: "", notes: "" });
          })}>
            Добавить пост
          </button>
        )}
        <Issues issues={issuesFor("guard_posts", issues)} />
      </fieldset>
      <fieldset>
        <legend>Точки на ситуационном плане (Г.5)</legend>
        {editable && (
          <div className="drill-grid">
            <Field label="Что ставит щелчок по плану">
              {(id) => (
                <select id={id} value={kind} onChange={(event) => setKind(event.target.value as LayoutPointKind)}>
                  {POINT_KINDS.map((item) => <option key={item.code} value={item.code}>{item.label}</option>)}
                </select>
              )}
            </Field>
            {kind === "guard_post" && (
              <Field label="Пост №" hint={posts.length ? undefined : "сначала добавьте пост"}>
                {(id) => (
                  <select id={id} value={ref} onChange={(event) => setPostRef(event.target.value)} disabled={!posts.length}>
                    {posts.map((code) => <option key={code} value={code}>{code}</option>)}
                  </select>
                )}
              </Field>
            )}
          </div>
        )}
        {graphics ? (
          <LayoutPlan graphics={graphics} points={form.points} kind={kind} postRef={ref} editable={editable} onPlace={place}
            onMove={(index, x, y) => edit((draft) => { draft.points[index].x = numberText(x); draft.points[index].y = numberText(y); })} />
        ) : (
          <small className="drill-hint">План строится по проверенному проекту — нажмите «Проверить».</small>
        )}
        {form.points.length > 0 && (
          <table className="drill-check mb-points" aria-label="Точки на плане">
            <thead><tr><th>Точка</th><th>X</th><th>Y</th><th>Подпись</th><th>До блока</th><th /></tr></thead>
            <tbody>
              {form.points.map((point, index) => {
                const distance = distances.get(`${point.kind}:${point.ref}:${Number(point.x.replace(",", "."))}:${Number(point.y.replace(",", "."))}`);
                return (
                  <tr key={index}>
                    <th scope="row">{KIND_LABEL[point.kind]}{point.kind === "guard_post" ? ` № ${point.ref}` : ""}</th>
                    <td>
                      <input aria-label="X" inputMode="decimal" value={point.x} disabled={disabled}
                        onChange={(event) => edit((draft) => { draft.points[index].x = event.target.value; })} />
                      {errors[`layout_points[${index}].x`] && <small className="form-error">{errors[`layout_points[${index}].x`]}</small>}
                    </td>
                    <td>
                      <input aria-label="Y" inputMode="decimal" value={point.y} disabled={disabled}
                        onChange={(event) => edit((draft) => { draft.points[index].y = event.target.value; })} />
                      {errors[`layout_points[${index}].y`] && <small className="form-error">{errors[`layout_points[${index}].y`]}</small>}
                    </td>
                    <td>
                      <input aria-label="Подпись" value={point.label} maxLength={300} disabled={disabled}
                        onChange={(event) => edit((draft) => { draft.points[index].label = event.target.value; })} />
                    </td>
                    <td>{distance === undefined || distance === null ? "—" : `${ruNum(distance, 0)} м`}</td>
                    <td>
                      {editable && (
                        <button type="button" className="link-button" onClick={() => edit((draft) => { draft.points.splice(index, 1); })}>
                          Удалить
                        </button>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
        <small className="drill-hint">Координаты — в системе координат объекта, как на чертеже маркшейдера (X — восток, Y — север).</small>
        <Issues issues={[...issuesFor("layout_points", issues), ...issuesFor("graphics", issues)]} />
      </fieldset>
    </>
  );
}
