"""Immutable snapshot builder for closed blasts.

A snapshot is a deep-copied training dataset. It never aliases the live
BlastDesign / BlastResult objects. Training must read snapshots only.
"""
from __future__ import annotations

import copy
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable

from design.models import ROLE_EXECUTED, ROLE_MEASURED, BlastDesign

from intelligence.datasets.features import FEATURE_SCHEMA_VERSION, extract_features
from intelligence.datasets.targets import extract_targets
from intelligence.datasets.validation import SampleValidation, validate_sample

DATASET_KIND = "training_snapshot"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _copy(value: Any) -> Any:
    return copy.deepcopy(value)


def sample_provenance(
    design: BlastDesign,
    *,
    site_id: str,
    feature_schema_version: str = FEATURE_SCHEMA_VERSION,
) -> dict[str, Any]:
    result = design.blast_result
    result_payload = result.provenance.to_dict() if result is not None else {}
    return {
        "source_blast_id": design.design_id,
        "source_design_updated_at": design.updated_at,
        "source_result_recorded_at": result.recorded_at if result is not None else "",
        "feature_schema_version": feature_schema_version,
        "site_id": site_id,
        "roles": {
            "design": "designed",
            "execution": ROLE_EXECUTED,
            "result": ROLE_MEASURED,
        },
        "execution_counts": {
            "as_drilled": len(design.as_drilled_holes),
            "as_charged": len(design.as_charged_holes),
            "as_fired": len(design.as_fired_holes),
        },
        "result_provenance": result_payload,
    }


@dataclass
class TrainingSample:
    """One closed blast frozen as features + targets + provenance."""

    source_blast_id: str
    site_id: str
    feature_schema_version: str
    features: dict[str, dict[str, Any]]
    targets: dict[str, dict[str, Any]]
    provenance: dict[str, Any]
    validation: SampleValidation

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_blast_id": self.source_blast_id,
            "site_id": self.site_id,
            "feature_schema_version": self.feature_schema_version,
            "features": _copy(self.features),
            "targets": _copy(self.targets),
            "provenance": _copy(self.provenance),
            "validation": self.validation.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> TrainingSample:
        data = data or {}
        validation_raw = data.get("validation") or {}
        return cls(
            source_blast_id=str(data.get("source_blast_id", "") or ""),
            site_id=str(data.get("site_id", "") or ""),
            feature_schema_version=str(data.get("feature_schema_version", FEATURE_SCHEMA_VERSION) or FEATURE_SCHEMA_VERSION),
            features=_copy(data.get("features") or {}),
            targets=_copy(data.get("targets") or {}),
            provenance=_copy(data.get("provenance") or {}),
            validation=SampleValidation(
                ok=bool(validation_raw.get("ok", False)),
                reasons=list(validation_raw.get("reasons") or []),
                closed=bool(validation_raw.get("closed", False)),
                complete_target_groups=list(validation_raw.get("complete_target_groups") or []),
            ),
        )


def build_sample(design: BlastDesign, *, site_id: str) -> TrainingSample:
    """Extract a candidate sample. Inclusion is decided by validate_sample."""
    features = extract_features(design, site_id=site_id)
    fired_coverage = (features.get("EXECUTION") or {}).get("fired_coverage")
    targets = extract_targets(design.blast_result, fired_coverage=fired_coverage)
    provenance = sample_provenance(design, site_id=site_id)
    validation = validate_sample(
        design=design,
        features=features,
        targets=targets,
        provenance=provenance,
        site_id=site_id,
    )
    return TrainingSample(
        source_blast_id=design.design_id,
        site_id=site_id,
        feature_schema_version=FEATURE_SCHEMA_VERSION,
        features=_copy(features),
        targets=_copy(targets),
        provenance=_copy(provenance),
        validation=validation,
    )


@dataclass
class DatasetSnapshot:
    """Write-once training dataset. Not a live view of production designs."""

    dataset_id: str
    dataset_version: int
    feature_schema_version: str
    source_blast_ids: list[str]
    created_at: str
    site_id: str
    name: str = ""
    kind: str = DATASET_KIND
    samples: list[TrainingSample] = field(default_factory=list)
    rejected: list[dict[str, Any]] = field(default_factory=list)
    immutable: bool = True

    @property
    def sample_count(self) -> int:
        return len(self.samples)

    @property
    def rejected_count(self) -> int:
        return len(self.rejected)

    def to_dict(self) -> dict[str, Any]:
        return {
            "dataset_id": self.dataset_id,
            "dataset_version": self.dataset_version,
            "feature_schema_version": self.feature_schema_version,
            "source_blast_ids": list(self.source_blast_ids),
            "created_at": self.created_at,
            "site_id": self.site_id,
            "name": self.name,
            "kind": DATASET_KIND,
            "sample_count": self.sample_count,
            "rejected_count": self.rejected_count,
            "samples": [sample.to_dict() for sample in self.samples],
            "rejected": _copy(self.rejected),
            "immutable": True,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> DatasetSnapshot:
        data = data or {}
        return cls(
            dataset_id=str(data.get("dataset_id", "") or ""),
            dataset_version=int(data.get("dataset_version", 1) or 1),
            feature_schema_version=str(
                data.get("feature_schema_version", FEATURE_SCHEMA_VERSION) or FEATURE_SCHEMA_VERSION
            ),
            source_blast_ids=[str(item) for item in data.get("source_blast_ids", [])],
            created_at=str(data.get("created_at", "") or ""),
            site_id=str(data.get("site_id", "") or ""),
            name=str(data.get("name", "") or ""),
            kind=DATASET_KIND,
            samples=[TrainingSample.from_dict(item) for item in data.get("samples", [])],
            rejected=_copy(data.get("rejected") or []),
            immutable=True,
        )

    def summary(self) -> dict[str, Any]:
        return {
            "dataset_id": self.dataset_id,
            "dataset_version": self.dataset_version,
            "feature_schema_version": self.feature_schema_version,
            "source_blast_ids": list(self.source_blast_ids),
            "created_at": self.created_at,
            "site_id": self.site_id,
            "name": self.name,
            "kind": DATASET_KIND,
            "sample_count": self.sample_count,
            "rejected_count": self.rejected_count,
            "immutable": True,
        }


def next_dataset_version(existing_versions: Iterable[int]) -> int:
    versions = [int(item) for item in existing_versions]
    return (max(versions) + 1) if versions else 1


def build_snapshot(
    designs: Iterable[BlastDesign],
    *,
    site_id: str,
    dataset_id: str,
    dataset_version: int,
    name: str = "",
    created_at: str = "",
) -> DatasetSnapshot:
    """Build an immutable snapshot. Incomplete blasts are listed, not included."""
    if not site_id:
        raise ValueError("Для снимка датасета нужен site_id.")
    dataset_id = str(dataset_id or "").strip() or uuid.uuid4().hex[:12]
    if int(dataset_version) < 1:
        raise ValueError("dataset_version должен быть >= 1.")

    samples: list[TrainingSample] = []
    rejected: list[dict[str, Any]] = []
    for design in designs:
        candidate = build_sample(design, site_id=site_id)
        if candidate.validation.ok:
            samples.append(candidate)
        else:
            rejected.append(
                {
                    "source_blast_id": design.design_id,
                    "reasons": list(candidate.validation.reasons),
                    "closed": candidate.validation.closed,
                }
            )

    snapshot = DatasetSnapshot(
        dataset_id=dataset_id,
        dataset_version=int(dataset_version),
        feature_schema_version=FEATURE_SCHEMA_VERSION,
        source_blast_ids=[sample.source_blast_id for sample in samples],
        created_at=created_at or utc_now_iso(),
        site_id=site_id,
        name=name,
        samples=samples,
        rejected=rejected,
        immutable=True,
    )
    return DatasetSnapshot.from_dict(snapshot.to_dict())
