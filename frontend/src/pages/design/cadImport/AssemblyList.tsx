// Участки сборки контура по порядку (TASK-013, PR 2): слой и объект, длина,
// разрыв до следующего участка и чем он закрыт — стыком (концы сведены, разрыв
// не больше допуска) или замыкающим отрезком; «развёрнут» — участок идёт
// против направления, в котором начерчен.
import { ruNumber } from "../../../lib/format";
import type { CadItemInfo } from "../../../types/cad";
import type { CadContourItem } from "../../../types/design";

function itemLabel(item: CadContourItem, info: CadItemInfo | undefined): string {
  if (item.kind === "segment") return "Отрезок";
  if (item.kind === "polyline") return item.label || "Построенная линия";
  return info?.layer ? `${info.layer} · ${item.handle}` : item.handle;
}

function linkLabel(info: CadItemInfo | undefined): string {
  if (!info) return "";
  const gap = ruNumber(info.gap_to_next_m, 2);
  return info.link === "closing" ? `замыкающий ${gap} м` : `стык ${gap} м`;
}

export function AssemblyList({
  items,
  info,
  selected,
  onSelect,
}: {
  items: CadContourItem[];
  /** Сведения сервера по участкам; пока предпросмотр не пришёл — пусто. */
  info: CadItemInfo[];
  selected: number | null;
  onSelect: (index: number) => void;
}) {
  return (
    <table className="cad-assembly" aria-label="Участки контура">
      <thead>
        <tr>
          <th scope="col">№</th>
          <th scope="col">Участок</th>
          <th scope="col">До следующего</th>
        </tr>
      </thead>
      <tbody>
        {items.map((item, index) => {
          const details = info[index];
          return (
            <tr
              key={`${index}:${item.kind}:${item.handle}`}
              className={`cad-assembly-row${selected === index ? " is-selected" : ""}`}
              onClick={() => onSelect(index)}
            >
              <td>{index + 1}</td>
              <td>
                <b>{itemLabel(item, details)}</b>
                <small>
                  {details ? `${ruNumber(details.length_m, 1)} м` : ""}
                  {details?.reversed ? " · развёрнут" : ""}
                </small>
              </td>
              <td className={details?.link === "closing" ? "is-closing" : ""}>{linkLabel(details)}</td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}
