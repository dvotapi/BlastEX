"""Исключения домена BlastEX для HTTP-слоя."""
from __future__ import annotations


class BlastExError(Exception):
    """Базовая ошибка расчёта или валидации домена."""

    def __init__(self, message: str, *, error_type: str = "calculation_error") -> None:
        super().__init__(message)
        self.message = message
        self.error_type = error_type


class WorkObjectNotFoundError(BlastExError):
    def __init__(self, name: str) -> None:
        super().__init__(
            f"Объект работ «{name}» не найден в справочнике.",
            error_type="work_object_not_found",
        )


class ScenarioNotFoundError(BlastExError):
    def __init__(self, scenario_id: str) -> None:
        super().__init__(
            f"Сценарий «{scenario_id}» не найден.",
            error_type="scenario_not_found",
        )


class InvalidGeometryError(BlastExError):
    def __init__(self, message: str) -> None:
        super().__init__(message, error_type="invalid_geometry")


class DesignNotFoundError(BlastExError):
    def __init__(self, design_id: str) -> None:
        super().__init__(
            f"Паспорт БВР «{design_id}» не найден.",
            error_type="design_not_found",
        )


class InvalidDesignError(BlastExError):
    def __init__(self, message: str) -> None:
        super().__init__(message, error_type="invalid_design")


class InvalidSurveyError(BlastExError):
    def __init__(self, message: str) -> None:
        super().__init__(message, error_type="invalid_survey")


class DatasetNotFoundError(BlastExError):
    def __init__(self, dataset_id: str) -> None:
        super().__init__(
            f"Снимок датасета «{dataset_id}» не найден.",
            error_type="dataset_not_found",
        )


class ImmutableDatasetError(BlastExError):
    def __init__(self, message: str) -> None:
        super().__init__(message, error_type="immutable_dataset")


class CalibrationNotFoundError(BlastExError):
    def __init__(self, model_id: str) -> None:
        super().__init__(
            f"Модель калибровки «{model_id}» не найдена.",
            error_type="calibration_not_found",
        )


class InvalidCalibrationError(BlastExError):
    def __init__(self, message: str) -> None:
        super().__init__(message, error_type="invalid_calibration")


class ImmutableCalibrationError(BlastExError):
    def __init__(self, message: str) -> None:
        super().__init__(message, error_type="immutable_calibration")


class OutcomeNotFoundError(BlastExError):
    def __init__(self, model_id: str) -> None:
        super().__init__(
            f"Модель исхода «{model_id}» не найдена.",
            error_type="outcome_not_found",
        )


class InvalidOutcomeError(BlastExError):
    def __init__(self, message: str) -> None:
        super().__init__(message, error_type="invalid_outcome")


class ImmutableOutcomeError(BlastExError):
    def __init__(self, message: str) -> None:
        super().__init__(message, error_type="immutable_outcome")


class DesignScenarioNotFoundError(BlastExError):
    def __init__(self, scenario_id: str) -> None:
        super().__init__(
            f"Сценарий проекта «{scenario_id}» не найден.",
            error_type="design_scenario_not_found",
        )


class InvalidDesignScenarioError(BlastExError):
    def __init__(self, message: str) -> None:
        super().__init__(message, error_type="invalid_design_scenario")
