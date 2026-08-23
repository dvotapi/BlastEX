"""Immutable training-dataset snapshots built from closed blasts.

Feature groups: SITE GEOLOGY GEOMETRY CHARGING TIMING EXECUTION ENVIRONMENT.
Target groups: FRAGMENTATION VIBRATION BLAST PERFORMANCE ECONOMICS.

Never train from mutable production records. Snapshots are write-once.
"""

from intelligence.datasets.builder import (
    DATASET_KIND,
    FEATURE_SCHEMA_VERSION,
    DatasetSnapshot,
    TrainingSample,
    build_sample,
    build_snapshot,
    next_dataset_version,
)
from intelligence.datasets.features import FEATURE_GROUPS, extract_features
from intelligence.datasets.persistence import (
    DatasetNotFoundError,
    ImmutableDatasetError,
    list_snapshots,
    load_snapshot,
    save_snapshot,
)
from intelligence.datasets.targets import TARGET_GROUPS, extract_targets
from intelligence.datasets.validation import (
    SampleValidation,
    is_closed_blast,
    validate_sample,
)

__all__ = [
    "DATASET_KIND",
    "FEATURE_GROUPS",
    "FEATURE_SCHEMA_VERSION",
    "TARGET_GROUPS",
    "DatasetNotFoundError",
    "DatasetSnapshot",
    "ImmutableDatasetError",
    "SampleValidation",
    "TrainingSample",
    "build_sample",
    "build_snapshot",
    "extract_features",
    "extract_targets",
    "is_closed_blast",
    "list_snapshots",
    "load_snapshot",
    "next_dataset_version",
    "save_snapshot",
    "validate_sample",
]
