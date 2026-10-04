import { describe, expect, it } from "vitest";
import type { DatasetSnapshot, DatasetSummary } from "./design";

// Проверка типов идёт через `tsc -b`: литерал с лишним полем или снимок,
// не совместимый со сводкой, не соберутся.
describe("DatasetSnapshot", () => {
  it("несёт базу baseline, как сводка снимка", () => {
    const snapshot: DatasetSnapshot = {
      dataset_id: "snap",
      dataset_version: 3,
      feature_schema_version: "1.0.0",
      source_blast_ids: ["blast-1"],
      created_at: "2026-10-03T00:00:00Z",
      site_id: "quarry-1",
      name: "Снимок",
      kind: "training_snapshot",
      sample_count: 1,
      rejected_count: 0,
      samples: [],
      rejected: [],
      immutable: true,
      fragmentation_base: { model: "kuzram", model_version: "2.1.0" },
    };
    const summary: DatasetSummary = snapshot;

    expect(summary.fragmentation_base.model_version).toBe("2.1.0");
  });
});
