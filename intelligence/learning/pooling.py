"""Pool immutable snapshots inside one tenant for global or site learning."""
from __future__ import annotations

import copy
import hashlib
from typing import Iterable

from intelligence.datasets.builder import DATASET_KIND, DatasetSnapshot, TrainingSample, utc_now_iso
from intelligence.datasets.features import FEATURE_SCHEMA_VERSION
from intelligence.learning.isolation import (
    assert_snapshots_for_scope,
    require_team_id,
    sample_site_id,
)
from intelligence.learning.types import SCOPE_GLOBAL, SCOPE_SITE


def _copy_sample(sample: TrainingSample) -> TrainingSample:
    return TrainingSample.from_dict(sample.to_dict())


def pooled_dataset_id(dataset_ids: Iterable[str]) -> str:
    joined = "+".join(sorted({str(item).strip() for item in dataset_ids if str(item).strip()}))
    digest = hashlib.sha256(joined.encode("utf-8")).hexdigest()[:12]
    return f"pooled-{digest}"


def pool_snapshots(
    snapshots: Iterable[DatasetSnapshot],
    *,
    team_id: str,
    scope: str,
    site_id: str = "",
    name: str = "",
) -> DatasetSnapshot:
    """Concatenate snapshots of one tenant. Never mixes another team's data."""
    require_team_id(team_id)
    frozen = assert_snapshots_for_scope(snapshots, team_id=team_id, scope=scope, site_id=site_id)
    samples: list[TrainingSample] = []
    rejected: list[dict] = []
    source_ids: list[str] = []
    dataset_ids: list[str] = []
    versions: list[int] = []
    schema = FEATURE_SCHEMA_VERSION

    for snapshot in frozen:
        dataset_ids.append(snapshot.dataset_id)
        versions.append(int(snapshot.dataset_version))
        if snapshot.feature_schema_version:
            schema = snapshot.feature_schema_version
        for sample in snapshot.samples:
            clone = _copy_sample(sample)
            if scope == SCOPE_SITE and sample_site_id(clone) not in {"", site_id}:
                continue
            samples.append(clone)
            if clone.source_blast_id and clone.source_blast_id not in source_ids:
                source_ids.append(clone.source_blast_id)
        rejected.extend(copy.deepcopy(snapshot.rejected or []))

    header_site = site_id if scope == SCOPE_SITE else ""
    pooled = DatasetSnapshot(
        dataset_id=pooled_dataset_id(dataset_ids) if len(dataset_ids) > 1 else dataset_ids[0],
        dataset_version=max(versions) if versions else 1,
        feature_schema_version=schema,
        source_blast_ids=source_ids,
        created_at=utc_now_iso(),
        site_id=header_site,
        name=name or ("global-pool" if scope == SCOPE_GLOBAL else f"site-{site_id}"),
        kind=DATASET_KIND,
        samples=samples,
        rejected=rejected,
        immutable=True,
    )
    return DatasetSnapshot.from_dict(pooled.to_dict())
