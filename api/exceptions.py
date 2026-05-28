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
