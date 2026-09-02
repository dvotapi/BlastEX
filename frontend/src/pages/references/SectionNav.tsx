import { useMemo, useState } from "react";
import type { ReferenceSchemaCatalog } from "../../types/referenceSchema";

export type SectionStat = {
  count: number;
  errors: number;
  warnings: number;
  changed: number;
};

/**
 * Навигатор разделов: группы приходят из схемы, счётчики — из черновика.
 * Поиск ищет и по разделам, и по записям, чтобы не приходилось помнить, в
 * каком разделе живёт «Взрывник».
 */
export function SectionNav({
  catalog,
  stats,
  active,
  onSelect,
  findRecord,
}: {
  catalog: ReferenceSchemaCatalog;
  stats: Record<string, SectionStat>;
  active: string;
  onSelect: (section: string, code?: string) => void;
  findRecord: (query: string) => Array<{ section: string; code: string; name: string }>;
}) {
  const [query, setQuery] = useState("");
  const trimmed = query.trim().toLowerCase();

  const sections = useMemo(
    () => Object.values(catalog.sections).filter((section) => !section.deprecated || (stats[section.code]?.count ?? 0) > 0),
    [catalog, stats],
  );

  const matches = useMemo(() => (trimmed.length >= 2 ? findRecord(trimmed).slice(0, 8) : []), [trimmed, findRecord]);

  return (
    <nav className="ref-nav">
      <input
        className="ref-nav-search"
        value={query}
        placeholder="Найти раздел или запись"
        onChange={(event) => setQuery(event.target.value)}
      />

      {matches.length > 0 && (
        <div className="ref-nav-matches">
          {matches.map((match) => (
            <button key={`${match.section}-${match.code}`} type="button" onClick={() => onSelect(match.section, match.code)}>
              <b>{match.name || match.code}</b>
              <span>{catalog.sections[match.section]?.label ?? match.section}</span>
            </button>
          ))}
        </div>
      )}

      {catalog.groups.map((group) => {
        const groupSections = sections.filter(
          (section) => section.group === group.code && (!trimmed || section.label.toLowerCase().includes(trimmed)),
        );
        if (!groupSections.length) return null;
        return (
          <div className="ref-nav-group" key={group.code}>
            <h5>{group.label}</h5>
            {groupSections.map((section) => {
              const stat = stats[section.code] ?? { count: 0, errors: 0, warnings: 0, changed: 0 };
              return (
                <button
                  key={section.code}
                  type="button"
                  className={section.code === active ? "active" : ""}
                  onClick={() => onSelect(section.code)}
                >
                  <span className="ref-nav-label">
                    {section.label}
                    {section.deprecated && <em> устарел</em>}
                  </span>
                  {stat.errors > 0 || stat.warnings > 0 ? (
                    <span className="ref-nav-badge warn">{stat.errors + stat.warnings}</span>
                  ) : (
                    <span className="ref-nav-badge">{stat.count}</span>
                  )}
                </button>
              );
            })}
          </div>
        );
      })}
    </nav>
  );
}
