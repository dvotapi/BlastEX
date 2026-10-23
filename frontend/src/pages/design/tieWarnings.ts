// Предупреждения построения схемы коммутации относятся к построенной сети.
// Хранятся вместе с её ключом и показываются, только пока в документе та же
// сеть: новое построение, отмена или правка связей их скрывают. Времена
// срабатывания (firing_events), которые дописывает анализ, сеть не меняют.
import { normalizeNetwork, type InitiationNetwork } from "../../types/design";

export type StoredTieWarnings = { networkKey: string; warnings: string[] };

function networkKey(network: InitiationNetwork): string {
  return JSON.stringify({ ...normalizeNetwork(network), firing_events: [] });
}

export function withTieWarnings(network: InitiationNetwork, warnings: string[]): StoredTieWarnings | null {
  return warnings.length ? { networkKey: networkKey(network), warnings } : null;
}

export function tieWarningsFor(stored: StoredTieWarnings | null, network: InitiationNetwork): string[] {
  if (!stored) return [];
  return networkKey(network) === stored.networkKey ? stored.warnings : [];
}
