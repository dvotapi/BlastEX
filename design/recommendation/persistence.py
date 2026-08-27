"""Write-once-friendly storage for design recommendations.

Files live in ``data/teams/{team_id}/recommendations/{design_id}/{id}.json``.
They are never written into ``designs/``. Saving a recommendation does not
call ``save_design`` and never marks the overlay as applied.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from cost.persistence import team_dir
from design.recommendation.types import DesignRecommendation

__all__ = [
    "RecommendationNotFoundError",
    "recommendations_dir",
    "list_recommendations",
    "load_recommendation",
    "save_recommendation",
]


class RecommendationNotFoundError(Exception):
    """Recommendation file is missing for this team / design."""


def recommendations_root(team_id: str) -> Path:
    return team_dir(team_id) / "recommendations"


def recommendations_dir(team_id: str, design_id: str) -> Path:
    _validate_id(design_id, "паспорт")
    return recommendations_root(team_id) / design_id


def _validate_id(value: str, label: str) -> None:
    if not value or value != Path(value).name or value in {".", ".."}:
        raise RecommendationNotFoundError(f"{label.capitalize()} «{value}» не найден.")


def recommendation_path(team_id: str, design_id: str, recommendation_id: str) -> Path:
    _validate_id(design_id, "паспорт")
    _validate_id(recommendation_id, "рекомендация")
    base = recommendations_dir(team_id, design_id).resolve()
    path = (base / f"{recommendation_id}.json").resolve()
    if not path.is_relative_to(base):
        raise RecommendationNotFoundError(f"Рекомендация «{recommendation_id}» не найдена.")
    return path


def list_recommendations(team_id: str, design_id: str) -> list[dict[str, Any]]:
    folder = recommendations_dir(team_id, design_id)
    if not folder.exists():
        return []
    items: list[dict[str, Any]] = []
    for path in sorted(folder.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        items.append(
            {
                "recommendation_id": str(data.get("recommendation_id", path.stem)),
                "design_id": str(data.get("design_id", design_id)),
                "profile": str(data.get("profile") or ""),
                "created_at": str(data.get("created_at", "")),
                "evaluated": int(data.get("evaluated") or 0),
                "pareto_count": int(data.get("pareto_count") or 0),
                "method": str(data.get("method") or ""),
                "auto_applied": False,
                "approved": False,
                "modifies_design": False,
                "replaces_design": False,
            }
        )
    items.sort(key=lambda item: item["created_at"])
    return items


def load_recommendation(team_id: str, design_id: str, recommendation_id: str) -> DesignRecommendation:
    path = recommendation_path(team_id, design_id, recommendation_id)
    if not path.exists():
        raise RecommendationNotFoundError(f"Рекомендация «{recommendation_id}» не найдена.")
    return DesignRecommendation.from_dict(json.loads(path.read_text(encoding="utf-8")))


def save_recommendation(team_id: str, result: DesignRecommendation) -> DesignRecommendation:
    if not result.recommendation_id:
        from design.recommendation.engine import new_recommendation_id

        result.recommendation_id = new_recommendation_id()
    result.auto_applied = False
    result.approved = False
    result.modifies_design = False
    result.replaces_design = False
    result.engineer_decides = True
    path = recommendation_path(team_id, result.design_id, result.recommendation_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    return result
