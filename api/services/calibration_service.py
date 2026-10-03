"""Train and apply residual calibration. Never auto-deploys to production."""
from __future__ import annotations

from typing import Any

from design.models import BlastDesign
from api.exceptions import (
    CalibrationNotFoundError,
    DatasetNotFoundError,
    ImmutableCalibrationError,
    ImmutableDatasetError,
    InvalidCalibrationError,
)
from api.schemas.calibration import (
    AlgorithmListResponse,
    CalibrationListResponse,
    CalibrationModelSchema,
    CalibrationPredictRequest,
    CalibrationPredictResponse,
    CalibrationProvenanceSchema,
    CalibrationStatusRequest,
    CalibrationSummarySchema,
    CalibrationTrainRequest,
)
from api.services.fragmentation_settings import resolve_kuzram_settings
from cost.v2.repository import EconomicsRepository
from intelligence.calibration.algorithms import DEFAULT_ALGORITHM, available_algorithms
from intelligence.calibration.base import (
    CURRENT_BASE,
    FRAGMENTATION_RESIDUALS,
    FragmentationBase,
    artifact_base,
    base_label,
    prediction_base,
    raw_base_name,
    refusal_reason,
    version_major,
)
from intelligence.calibration.persistence import (
    CalibrationNotFoundError as StoreNotFound,
    ImmutableCalibrationError as StoreImmutable,
)
from intelligence.calibration.persistence import (
    existing_versions,
    list_models,
    load_model,
    new_model_id,
    production_model,
    save_model,
    set_status,
)
from intelligence.calibration.prediction import (
    apply_residual,
    baseline_without_model,
    empirical_baseline,
    features_from_design,
)
from intelligence.calibration.training import next_model_version, train_from_snapshot
from intelligence.calibration.types import STATUS_CANDIDATE, normalize_model_type
from intelligence.datasets import persistence as dataset_persistence
from simulation.fragmentation.engine import resolve_model


def _model_schema(model) -> CalibrationModelSchema:
    payload = model.to_dict()
    payload.pop("estimator", None)
    payload.pop("training_matrix", None)
    payload["base_label"] = base_label(model.model_type, model.baseline_model, model.baseline_model_version)
    return CalibrationModelSchema(**payload)


def _predict_schema(payload: dict[str, Any]) -> CalibrationPredictResponse:
    provenance = CalibrationProvenanceSchema(**payload.get("provenance") or {})
    data = dict(payload)
    data["provenance"] = provenance
    data["modifies_design"] = False
    data["applied_as"] = "recommendation_overlay"
    return CalibrationPredictResponse(**data)


def list_algorithms() -> AlgorithmListResponse:
    return AlgorithmListResponse(items=available_algorithms(), default=DEFAULT_ALGORITHM)


def list_calibration_models(team_id: str) -> CalibrationListResponse:
    items = list_models(team_id)
    return CalibrationListResponse(
        items=[CalibrationSummarySchema(**item.__dict__) for item in items]
    )


def get_calibration_model(team_id: str, model_id: str) -> CalibrationModelSchema:
    try:
        model = load_model(team_id, model_id)
    except StoreNotFound as exc:
        raise CalibrationNotFoundError(model_id) from exc
    except StoreImmutable as exc:
        raise ImmutableCalibrationError(str(exc)) from exc
    return _model_schema(model)


def train_calibration(team_id: str, request: CalibrationTrainRequest) -> CalibrationModelSchema:
    dataset_id = request.dataset_id.strip()
    if not dataset_id:
        raise InvalidCalibrationError("Для обучения нужен dataset_id неизменяемого снимка.")
    try:
        snapshot = dataset_persistence.load_snapshot(team_id, dataset_id)
    except dataset_persistence.DatasetNotFoundError as exc:
        raise DatasetNotFoundError(dataset_id) from exc
    except dataset_persistence.ImmutableDatasetError as exc:
        raise ImmutableDatasetError(str(exc)) from exc

    try:
        model_type = normalize_model_type(request.model_type)
        site_id = (request.site_id or snapshot.site_id).strip()
        model = train_from_snapshot(
            snapshot,
            model_type=model_type,
            algorithm=request.algorithm or DEFAULT_ALGORITHM,
            model_id=new_model_id(),
            model_version=next_model_version(existing_versions(team_id, site_id, model_type)),
            site_id=site_id,
        )
        saved = save_model(team_id, model)
    except ValueError as exc:
        raise InvalidCalibrationError(str(exc)) from exc
    except StoreImmutable as exc:
        raise ImmutableCalibrationError(str(exc)) from exc
    if saved.status != STATUS_CANDIDATE:
        raise InvalidCalibrationError("Новая модель должна сохраняться со статусом candidate.")
    return _model_schema(saved)


def update_status(team_id: str, model_id: str, request: CalibrationStatusRequest) -> CalibrationModelSchema:
    try:
        model = set_status(team_id, model_id, request.status)
    except StoreNotFound as exc:
        raise CalibrationNotFoundError(model_id) from exc
    except StoreImmutable as exc:
        raise ImmutableCalibrationError(str(exc)) from exc
    except ValueError as exc:
        raise InvalidCalibrationError(str(exc)) from exc
    return _model_schema(model)


def _design_from_request(request: CalibrationPredictRequest) -> BlastDesign | None:
    if request.design is None:
        return None
    return BlastDesign.from_dict(request.design.model_dump())


def _provided_base(request: CalibrationPredictRequest) -> tuple[FragmentationBase | None, str]:
    """База присланного baseline кусковатости; без неё — причина отказа.

    Модель и версию клиент называет сам, поэтому они проверяются строже, чем
    записанные сервером: пустая или нераспознанная версия — отказ, а не
    старая база, как у prediction_base.
    """
    model = request.baseline_model.strip()
    version = request.baseline_model_version.strip()
    if not model or not version:
        return None, "Не указано, какой моделью и версией посчитан baseline, — калибровка кусковатости не применена."
    try:
        model_id = resolve_model(model)
    except ValueError:
        return None, f"Неизвестная модель baseline «{model}» — калибровка кусковатости не применена."
    if version_major(version) is None:
        return None, f"Версия модели baseline «{version}» не распознана — калибровка кусковатости не применена."
    return prediction_base(model_id, version), ""


def _artifact_base(model) -> tuple[FragmentationBase, str]:
    """База артефакта кусковатости; неизвестная модель базы — текущая база и причина отказа."""
    try:
        return artifact_base(model.baseline_model, model.baseline_model_version), ""
    except ValueError:
        name = raw_base_name(model.baseline_model, model.baseline_model_version)
        return CURRENT_BASE, (
            f"Калибровка обучена на прогнозах неизвестной модели «{name}» и не применяется — её нужно переобучить."
        )


def _load_requested_model(team_id: str, request: CalibrationPredictRequest, model_type: str, site_id: str):
    try:
        if request.model_id.strip():
            return load_model(team_id, request.model_id.strip())
        if request.use_production:
            if not site_id:
                raise InvalidCalibrationError("Для производственной модели нужен site_id.")
            return production_model(team_id, site_id, model_type)
    except StoreNotFound as exc:
        raise CalibrationNotFoundError(request.model_id) from exc
    except StoreImmutable as exc:
        raise ImmutableCalibrationError(str(exc)) from exc
    return None


def predict_calibration(
    team_id: str,
    request: CalibrationPredictRequest,
    *,
    repository: EconomicsRepository | None = None,
) -> CalibrationPredictResponse:
    try:
        model_type = normalize_model_type(request.model_type)
    except ValueError as exc:
        raise InvalidCalibrationError(str(exc)) from exc

    design = _design_from_request(request)
    site_id = request.site_id.strip()
    if not site_id and design is not None:
        site_id = str((request.features or {}).get("SITE", {}).get("site_id") or "")

    model = _load_requested_model(team_id, request, model_type, site_id)
    fragmentation = model_type in FRAGMENTATION_RESIDUALS
    # Baseline кусковатости считается базой артефакта, а без артефакта — текущей.
    base, refusal = CURRENT_BASE, ""
    if model is not None and fragmentation:
        base, refusal = _artifact_base(model)

    baseline = request.baseline
    baseline_source = "provided" if baseline is not None else ""
    value_base: FragmentationBase | None = None
    baseline_warnings: list[str] = []
    if baseline is not None:
        if model is not None and fragmentation and not refusal:
            value_base, refusal = _provided_base(request)
    elif design is not None:
        # Настройки читаются из хранилища лениво: сохранённый совместимый
        # прогноз берётся как есть, и пересчёт не нужен.
        def resolve_fallback() -> tuple[Any, dict[str, Any]]:
            resolved = resolve_kuzram_settings(
                explicit=None, work_object_name="", organization_id=team_id, repository=repository
            )
            return resolved.settings, resolved.source_payload()

        baseline, baseline_source, value_base, baseline_warnings = empirical_baseline(
            design,
            model_type,
            base=base,
            resolve_fallback=resolve_fallback if fragmentation and not base.legacy else None,
        )
    if baseline is None:
        raise InvalidCalibrationError(
            "Для прогноза калибровки нужен baseline (Kuz-Ram / PPV) или паспорт с эмпирическим прогнозом."
        )
    # Присланный и посчитанный сервером baseline сверяются с базой артефакта
    # одним правилом: пересчёт идёт текущей версией модели движка, а
    # артефакт мог быть обучен на другой.
    if model is not None and fragmentation and not refusal:
        refusal = refusal_reason(model_type, base, value_base)

    features: dict[str, Any] = dict(request.features or {})
    if not features and design is not None:
        features = features_from_design(design, site_id=site_id or "unknown")

    if model is None:
        reason = "Нет выбранной модели калибровки."
        if request.use_production:
            reason = f"Нет production-модели «{model_type}» для площадки «{site_id}»."
        payload = baseline_without_model(
            baseline=float(baseline),
            model_type=model_type,
            site_id=site_id,
            baseline_source=baseline_source,
            reason=reason,
        )
        return _predict_schema(_with_warnings(payload.to_dict(), baseline_warnings))

    if site_id and model.site_id != site_id:
        raise InvalidCalibrationError("site_id запроса не совпадает с площадкой модели.")
    if model.model_type != model_type:
        raise InvalidCalibrationError("Тип модели не совпадает с запросом прогноза.")
    if refusal:
        payload = baseline_without_model(
            baseline=float(baseline),
            model_type=model_type,
            site_id=site_id,
            baseline_source=baseline_source,
            reason=refusal,
        )
        return _predict_schema(_with_warnings(payload.to_dict(), baseline_warnings))

    try:
        prediction = apply_residual(
            model,
            features=features,
            baseline=float(baseline),
            baseline_source=baseline_source,
        )
    except ValueError as exc:
        raise InvalidCalibrationError(str(exc)) from exc
    payload = prediction.to_dict()
    payload["modifies_design"] = False
    return _predict_schema(_with_warnings(payload, baseline_warnings))


def _with_warnings(payload: dict[str, Any], baseline_warnings: list[str]) -> dict[str, Any]:
    """Предупреждения пересчёта baseline — после причины отказа и прочих, без дублей."""
    warnings = list(payload.get("warnings") or [])
    warnings.extend(item for item in dict.fromkeys(baseline_warnings) if item not in warnings)
    payload["warnings"] = warnings
    return payload
