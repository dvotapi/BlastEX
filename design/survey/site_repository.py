"""Съёмка старого блока на объекте: хранение (TASK-014, PR 5а).

Блока нет в проектах BlastEX, есть только точки маркшейдера. Записи
организации, неизменяемые: загрузить заново и удалить. Тот же файл для того
же блока второй раз не принимается (уникальный индекс в PostgreSQL).
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from threading import Lock
from typing import Any, Protocol
from uuid import uuid4

from sqlalchemy import Date, DateTime, Index, Numeric, String, Text, create_engine, delete, desc, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Mapped, mapped_column, sessionmaker

from cost.v2.db_repository import Base, JsonType, SCHEMA


class SiteSurveyError(RuntimeError):
    pass


class SiteSurveyNotFoundError(SiteSurveyError):
    pass


class SiteSurveyDuplicateError(SiteSurveyError):
    pass


class SiteSurveyRow(Base):
    __tablename__ = "site_surveys"
    __table_args__ = (
        Index("ix_site_surveys_org_site_date", "organization_id", "site_code", text("survey_date DESC")),
        Index("uq_site_surveys_file", "organization_id", "site_code", "block_label", "file_sha256", unique=True),
        {"schema": SCHEMA},
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    organization_id: Mapped[str] = mapped_column(String(120), nullable=False)
    site_code: Mapped[str] = mapped_column(Text, nullable=False)
    block_label: Mapped[str] = mapped_column(Text, nullable=False)
    horizon_m: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    survey_date: Mapped[date] = mapped_column(Date, nullable=False)
    file_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    file_sha256: Mapped[str | None] = mapped_column(Text, nullable=True)
    points: Mapped[list[dict[str, Any]]] = mapped_column(JsonType, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_by: Mapped[str | None] = mapped_column(Text, nullable=True)


class SiteSurveyRepository(Protocol):
    def list(self, organization_id: str, site_code: str) -> list[dict[str, Any]]: ...

    def get(self, organization_id: str, survey_id: str) -> dict[str, Any]: ...

    def create(self, organization_id: str, actor: str, record: dict[str, Any]) -> dict[str, Any]: ...

    def delete(self, organization_id: str, survey_id: str) -> None: ...


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def _not_found(survey_id: str) -> SiteSurveyNotFoundError:
    return SiteSurveyNotFoundError(f"Съёмка {survey_id} не найдена.")


def _duplicate() -> SiteSurveyDuplicateError:
    return SiteSurveyDuplicateError("Этот файл уже загружен")


def _sorted(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Свежие съёмки первыми; при равной дате — позже загруженная."""

    return sorted(records, key=lambda r: (r["survey_date"], r["created_at"]), reverse=True)


class PostgresSiteSurveyRepository:
    def __init__(self, database_url: str) -> None:
        self.engine = create_engine(database_url, pool_pre_ping=True, future=True)
        self.session_factory = sessionmaker(self.engine, expire_on_commit=False, future=True)

    @staticmethod
    def _record(row: SiteSurveyRow) -> dict[str, Any]:
        return {
            "id": row.id,
            "site_code": row.site_code,
            "block_label": row.block_label,
            "horizon_m": float(row.horizon_m) if row.horizon_m is not None else None,
            "survey_date": row.survey_date.isoformat(),
            "file_name": row.file_name,
            "file_sha256": row.file_sha256,
            "points": list(row.points or []),
            "created_at": row.created_at.isoformat(),
            "created_by": row.created_by,
        }

    def list(self, organization_id: str, site_code: str) -> list[dict[str, Any]]:
        with self.session_factory() as session:
            rows = session.scalars(
                select(SiteSurveyRow)
                .where(SiteSurveyRow.organization_id == organization_id, SiteSurveyRow.site_code == site_code)
                .order_by(desc(SiteSurveyRow.survey_date), desc(SiteSurveyRow.created_at))
            ).all()
            return [self._record(row) for row in rows]

    def get(self, organization_id: str, survey_id: str) -> dict[str, Any]:
        with self.session_factory() as session:
            row = session.get(SiteSurveyRow, survey_id)
            if row is None or row.organization_id != organization_id:
                raise _not_found(survey_id)
            return self._record(row)

    def create(self, organization_id: str, actor: str, record: dict[str, Any]) -> dict[str, Any]:
        row = SiteSurveyRow(
            id=str(uuid4()),
            organization_id=organization_id,
            site_code=record["site_code"],
            block_label=record["block_label"],
            horizon_m=record.get("horizon_m"),
            survey_date=date.fromisoformat(record["survey_date"]),
            file_name=record.get("file_name"),
            file_sha256=record.get("file_sha256"),
            points=list(record["points"]),
            created_at=_now(),
            created_by=actor or None,
        )
        try:
            with self.session_factory() as session, session.begin():
                session.add(row)
        except IntegrityError as exc:
            raise _duplicate() from exc
        return self._record(row)

    def delete(self, organization_id: str, survey_id: str) -> None:
        with self.session_factory() as session, session.begin():
            deleted = session.execute(
                delete(SiteSurveyRow).where(
                    SiteSurveyRow.id == survey_id, SiteSurveyRow.organization_id == organization_id
                )
            ).rowcount
            if not deleted:
                raise _not_found(survey_id)


class InMemorySiteSurveyRepository:
    """Для тестов API: тот же контракт, что у PostgreSQL-репозитория."""

    def __init__(self) -> None:
        self._records: dict[str, tuple[str, dict[str, Any]]] = {}
        self._lock = Lock()

    def list(self, organization_id: str, site_code: str) -> list[dict[str, Any]]:
        with self._lock:
            found = [
                dict(record)
                for org, record in self._records.values()
                if org == organization_id and record["site_code"] == site_code
            ]
        return _sorted(found)

    def get(self, organization_id: str, survey_id: str) -> dict[str, Any]:
        with self._lock:
            item = self._records.get(survey_id)
            if item is None or item[0] != organization_id:
                raise _not_found(survey_id)
            return dict(item[1])

    def create(self, organization_id: str, actor: str, record: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            sha = record.get("file_sha256")
            if sha is not None and any(
                org == organization_id
                and old["site_code"] == record["site_code"]
                and old["block_label"] == record["block_label"]
                and old["file_sha256"] == sha
                for org, old in self._records.values()
            ):
                raise _duplicate()
            created = {
                "id": str(uuid4()),
                "site_code": record["site_code"],
                "block_label": record["block_label"],
                "horizon_m": record.get("horizon_m"),
                "survey_date": record["survey_date"],
                "file_name": record.get("file_name"),
                "file_sha256": sha,
                "points": list(record["points"]),
                "created_at": _now().isoformat(),
                "created_by": actor or None,
            }
            self._records[created["id"]] = (organization_id, created)
            return dict(created)

    def delete(self, organization_id: str, survey_id: str) -> None:
        with self._lock:
            item = self._records.get(survey_id)
            if item is None or item[0] != organization_id:
                raise _not_found(survey_id)
            del self._records[survey_id]

