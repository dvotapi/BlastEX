/**
 * Имя объекта в списке паспортов: паспорт фиксирует `reference_revision_id`,
 * поэтому его объект должен подписываться по справочнику ТОЙ ревизии, а не
 * текущего снимка — иначе переименованный (или удалённый) объект подменяет
 * подпись старого паспорта чужим именем. Так же считает и вкладка
 * «Экономика» (BlockEconomicsPage), которая явно грузит исторический снимок.
 */
import type { TechnicalPassport } from "../../types/blockEconomics";

/** revisionId -> (код объекта -> имя объекта на момент этой ревизии). */
export type SiteNamesByRevision = Record<string, Record<string, string>>;

/** Код объекта -> имя по текущему (последнему опубликованному) снимку. */
export type CurrentSiteNames = Record<string, string>;

/**
 * Различные `reference_revision_id` паспортов — по одному снимку на ревизию,
 * а не на паспорт: несколько паспортов часто ссылаются на одну ревизию.
 */
export function distinctRevisionIds(passports: TechnicalPassport[]): string[] {
  const seen = new Set<string>();
  for (const passport of passports) {
    if (passport.reference_revision_id) seen.add(passport.reference_revision_id);
  }
  return Array.from(seen);
}

/**
 * Имя объекта для паспорта: сперва — по его собственной ревизии справочников,
 * затем — по текущему снимку (ревизия неизвестна или не загрузилась), и
 * только в последнюю очередь — код объекта, если имя не нашлось нигде.
 */
export function siteNameFor(
  passport: TechnicalPassport,
  namesByRevision: SiteNamesByRevision,
  currentNames: CurrentSiteNames,
): string {
  const ownRevisionName = namesByRevision[passport.reference_revision_id]?.[passport.site_code];
  if (ownRevisionName) return ownRevisionName;
  return currentNames[passport.site_code] ?? passport.site_code;
}
