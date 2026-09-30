"""Хранение импорта чертежа: источники, сущности и шаблон слоёв объекта.

Источник — один загруженный файл вместе с исходными байтами: повторный
разбор (другой масштаб, радиус подписей, подошва) читает его заново, не
прося файл у пользователя. Шаблон слоёв (имя слоя → роль) живёт на объекте:
следующий файл того же маркшейдера размечается по нему сам.

Каждый метод принимает организацию первым аргументом и фильтрует по ней —
чужой источник для репозитория не существует.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field, replace
from datetime import date, datetime, timezone
from typing import Any, Protocol

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    create_engine,
    delete,
    insert,
    select,
    update,
)
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Mapped, deferred, mapped_column, sessionmaker

from cost.v2.db_repository import SCHEMA, Base, JsonType
from design.spatial.cad.model import CadEntity
from design.spatial.cad.roles import TemplateEntry, layer_key


class CadSourceNotFound(LookupError):
    """Источника нет в этой организации."""


@dataclass
class CadSourceRecord:
    id: str
    site_code: str
    work_object_name: str
    file_name: str
    file_format: str
    file_size: int
    file_sha256: str
    params: dict[str, Any]
    summary: dict[str, Any]
    uploaded_by: str
    uploaded_at: datetime
    survey_date: date | None = None
    coordinate_system: dict[str, Any] | None = None
    file_data: bytes | None = field(default=None, repr=False)


class CadRepository(Protocol):
    def create_sources(
        self, organization_id: str, items: list[tuple[CadSourceRecord, list[CadEntity]]]
    ) -> None: ...

    def get_source(self, organization_id: str, source_id: str, *, with_file: bool = False) -> CadSourceRecord | None: ...

    def list_entities(self, organization_id: str, source_id: str) -> list[CadEntity]: ...

    def replace_entities(
        self,
        organization_id: str,
        source_id: str,
        entities: list[CadEntity],
        params: dict[str, Any],
        summary: dict[str, Any],
    ) -> None: ...

    def update_roles(
        self,
        organization_id: str,
        source_id: str,
        roles: dict[str, tuple[str, str]],
        summary: dict[str, Any],
    ) -> None: ...

    def get_layer_template(self, organization_id: str, site_code: str) -> dict[str, TemplateEntry]: ...

    def add_missing_layer_roles(self, organization_id: str, site_code: str, roles: dict[str, str], actor: str) -> None: ...

    def upsert_layer_roles(self, organization_id: str, site_code: str, roles: dict[str, str], actor: str) -> None: ...


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def _template_rows(roles: dict[str, str]) -> dict[str, tuple[str, str]]:
    """Ключ слоя → (имя, роль); при совпадении ключей побеждает последний."""

    return {layer_key(name): (name, role) for name, role in roles.items() if layer_key(name)}


# --- PostgreSQL ---------------------------------------------------------


class CadSourceRow(Base):
    __tablename__ = "cad_sources"
    __table_args__ = (
        Index("ix_cad_sources_org_site_uploaded", "organization_id", "site_code", "uploaded_at"),
        {"schema": SCHEMA},
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    organization_id: Mapped[str] = mapped_column(String(120), nullable=False)
    site_code: Mapped[str] = mapped_column(String(80), nullable=False, default="")
    work_object_name: Mapped[str] = mapped_column(String(300), nullable=False, default="")
    file_name: Mapped[str] = mapped_column(String(300), nullable=False)
    file_format: Mapped[str] = mapped_column(String(8), nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)
    file_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    # Исходник читается только для повторного разбора.
    file_data: Mapped[bytes] = deferred(mapped_column(LargeBinary, nullable=False))
    survey_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    coordinate_system: Mapped[dict[str, Any] | None] = mapped_column(JsonType, nullable=True)
    params: Mapped[dict[str, Any]] = mapped_column(JsonType, nullable=False)
    summary: Mapped[dict[str, Any]] = mapped_column(JsonType, nullable=False)
    uploaded_by: Mapped[str] = mapped_column(String(320), nullable=False)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class CadEntityRow(Base):
    __tablename__ = "cad_entities"
    __table_args__ = (
        Index("ix_cad_entities_org_source_seq", "organization_id", "source_id", "seq"),
        {"schema": SCHEMA},
    )

    source_id: Mapped[str] = mapped_column(
        String(36), ForeignKey(f"{SCHEMA}.cad_sources.id", ondelete="CASCADE"), primary_key=True
    )
    handle: Mapped[str] = mapped_column(String(64), primary_key=True)
    organization_id: Mapped[str] = mapped_column(String(120), nullable=False)
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    layer: Mapped[str] = mapped_column(String(255), nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    role_origin: Mapped[str] = mapped_column(String(16), nullable=False)
    geometry: Mapped[dict[str, Any]] = mapped_column(JsonType, nullable=False)
    closed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    vertex_count: Mapped[int] = mapped_column(Integer, nullable=False)
    length_m: Mapped[float] = mapped_column(Float, nullable=False)
    z_kind: Mapped[str] = mapped_column(String(8), nullable=False)
    z_min: Mapped[float] = mapped_column(Float, nullable=False)
    z_max: Mapped[float] = mapped_column(Float, nullable=False)
    attributes: Mapped[dict[str, Any]] = mapped_column(JsonType, nullable=False)


class CadLayerRoleRow(Base):
    __tablename__ = "cad_layer_roles"
    __table_args__ = ({"schema": SCHEMA},)

    organization_id: Mapped[str] = mapped_column(String(120), primary_key=True)
    site_code: Mapped[str] = mapped_column(String(80), primary_key=True)
    layer_key: Mapped[str] = mapped_column(String(255), primary_key=True)
    layer_name: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    manual: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    updated_by: Mapped[str] = mapped_column(String(320), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


def _entity_rows(organization_id: str, source_id: str, entities: list[CadEntity]) -> list[dict[str, Any]]:
    return [
        {
            "source_id": source_id,
            "handle": item.handle,
            "organization_id": organization_id,
            "seq": index,
            "layer": item.layer,
            "kind": item.kind,
            "role": item.role,
            "role_origin": item.role_origin,
            "geometry": item.geometry(),
            "closed": item.closed,
            "vertex_count": item.vertex_count,
            "length_m": item.length_m,
            "z_kind": item.z_kind,
            "z_min": item.z_min,
            "z_max": item.z_max,
            "attributes": item.attributes(),
        }
        for index, item in enumerate(entities)
    ]


def _entity(row: CadEntityRow) -> CadEntity:
    return CadEntity.restore(
        handle=row.handle,
        layer=row.layer,
        kind=row.kind,
        geometry=row.geometry,
        closed=row.closed,
        attributes=row.attributes or {},
        role=row.role,
        role_origin=row.role_origin,
    )


class PostgresCadRepository:
    def __init__(self, database_url: str) -> None:
        self.engine = create_engine(database_url, pool_pre_ping=True, future=True)
        self.session_factory = sessionmaker(self.engine, expire_on_commit=False, future=True)

    def create_sources(
        self, organization_id: str, items: list[tuple[CadSourceRecord, list[CadEntity]]]
    ) -> None:
        """Все файлы одной загрузки — одной транзакцией: либо все, либо ни одного."""

        with self.session_factory() as session, session.begin():
            for record, entities in items:
                session.add(
                    CadSourceRow(
                        id=record.id,
                        organization_id=organization_id,
                        site_code=record.site_code,
                        work_object_name=record.work_object_name,
                        file_name=record.file_name,
                        file_format=record.file_format,
                        file_size=record.file_size,
                        file_sha256=record.file_sha256,
                        file_data=record.file_data or b"",
                        survey_date=record.survey_date,
                        coordinate_system=record.coordinate_system,
                        params=record.params,
                        summary=record.summary,
                        uploaded_by=record.uploaded_by,
                        uploaded_at=record.uploaded_at,
                    )
                )
                session.flush()
                if entities:
                    session.execute(insert(CadEntityRow), _entity_rows(organization_id, record.id, entities))

    def get_source(self, organization_id: str, source_id: str, *, with_file: bool = False) -> CadSourceRecord | None:
        with self.session_factory() as session:
            row = session.execute(
                select(CadSourceRow).where(
                    CadSourceRow.organization_id == organization_id, CadSourceRow.id == source_id
                )
            ).scalar_one_or_none()
            if row is None:
                return None
            return CadSourceRecord(
                id=row.id,
                site_code=row.site_code,
                work_object_name=row.work_object_name,
                file_name=row.file_name,
                file_format=row.file_format,
                file_size=row.file_size,
                file_sha256=row.file_sha256,
                params=row.params,
                summary=row.summary,
                uploaded_by=row.uploaded_by,
                uploaded_at=row.uploaded_at,
                survey_date=row.survey_date,
                coordinate_system=row.coordinate_system,
                file_data=bytes(row.file_data) if with_file else None,
            )

    def list_entities(self, organization_id: str, source_id: str) -> list[CadEntity]:
        with self.session_factory() as session:
            rows = session.execute(
                select(CadEntityRow)
                .where(CadEntityRow.organization_id == organization_id, CadEntityRow.source_id == source_id)
                .order_by(CadEntityRow.seq)
            ).scalars()
            return [_entity(row) for row in rows]

    def replace_entities(
        self,
        organization_id: str,
        source_id: str,
        entities: list[CadEntity],
        params: dict[str, Any],
        summary: dict[str, Any],
    ) -> None:
        with self.session_factory() as session, session.begin():
            self._require(session, organization_id, source_id)
            session.execute(
                delete(CadEntityRow).where(
                    CadEntityRow.organization_id == organization_id, CadEntityRow.source_id == source_id
                )
            )
            if entities:
                session.execute(insert(CadEntityRow), _entity_rows(organization_id, source_id, entities))
            session.execute(
                update(CadSourceRow)
                .where(CadSourceRow.organization_id == organization_id, CadSourceRow.id == source_id)
                .values(params=params, summary=summary)
            )

    def update_roles(
        self,
        organization_id: str,
        source_id: str,
        roles: dict[str, tuple[str, str]],
        summary: dict[str, Any],
    ) -> None:
        with self.session_factory() as session, session.begin():
            self._require(session, organization_id, source_id)
            if roles:
                # Одна массовая операция по первичному ключу: смена роли слоя
                # из десятков тысяч точек — не десятки тысяч запросов. Источник
                # уже проверен на принадлежность организации.
                session.execute(
                    update(CadEntityRow).where(CadEntityRow.organization_id == organization_id),
                    [
                        {"source_id": source_id, "handle": handle, "role": role, "role_origin": origin}
                        for handle, (role, origin) in roles.items()
                    ],
                    # Объекты строк в сессию не загружались — синхронизировать нечего.
                    execution_options={"synchronize_session": None},
                )
            session.execute(
                update(CadSourceRow)
                .where(CadSourceRow.organization_id == organization_id, CadSourceRow.id == source_id)
                .values(summary=summary)
            )

    def get_layer_template(self, organization_id: str, site_code: str) -> dict[str, TemplateEntry]:
        with self.session_factory() as session:
            rows = session.execute(
                select(CadLayerRoleRow).where(
                    CadLayerRoleRow.organization_id == organization_id, CadLayerRoleRow.site_code == site_code
                )
            ).scalars()
            return {row.layer_key: TemplateEntry(row.role, row.manual) for row in rows}

    def add_missing_layer_roles(self, organization_id: str, site_code: str, roles: dict[str, str], actor: str) -> None:
        self._write_template(organization_id, site_code, roles, actor, overwrite=False)

    def upsert_layer_roles(self, organization_id: str, site_code: str, roles: dict[str, str], actor: str) -> None:
        self._write_template(organization_id, site_code, roles, actor, overwrite=True)

    def _write_template(
        self, organization_id: str, site_code: str, roles: dict[str, str], actor: str, *, overwrite: bool
    ) -> None:
        rows = [
            {
                "organization_id": organization_id,
                "site_code": site_code,
                "layer_key": key,
                "layer_name": name,
                "role": role,
                # Пополнение при загрузке — догадка; ручная правка — подтверждение.
                "manual": overwrite,
                "updated_by": actor,
                "updated_at": _now(),
            }
            for key, (name, role) in _template_rows(roles).items()
        ]
        if not rows:
            return
        statement = pg_insert(CadLayerRoleRow).values(rows)
        keys = [CadLayerRoleRow.organization_id, CadLayerRoleRow.site_code, CadLayerRoleRow.layer_key]
        if overwrite:
            statement = statement.on_conflict_do_update(
                index_elements=keys,
                set_={
                    "layer_name": statement.excluded.layer_name,
                    "role": statement.excluded.role,
                    "manual": statement.excluded.manual,
                    "updated_by": statement.excluded.updated_by,
                    "updated_at": statement.excluded.updated_at,
                },
            )
        else:
            statement = statement.on_conflict_do_nothing(index_elements=keys)
        with self.session_factory() as session, session.begin():
            session.execute(statement)

    @staticmethod
    def _require(session, organization_id: str, source_id: str) -> None:
        found = session.execute(
            select(CadSourceRow.id).where(CadSourceRow.organization_id == organization_id, CadSourceRow.id == source_id)
        ).scalar_one_or_none()
        if found is None:
            raise CadSourceNotFound(source_id)


# --- в памяти (тесты и стенд) -------------------------------------------


class InMemoryCadRepository:
    def __init__(self) -> None:
        self._sources: dict[tuple[str, str], CadSourceRecord] = {}
        self._entities: dict[tuple[str, str], list[CadEntity]] = {}
        self._templates: dict[tuple[str, str], dict[str, tuple[str, TemplateEntry]]] = {}

    def create_sources(
        self, organization_id: str, items: list[tuple[CadSourceRecord, list[CadEntity]]]
    ) -> None:
        for record, entities in items:
            self._sources[(organization_id, record.id)] = copy.deepcopy(record)
            self._entities[(organization_id, record.id)] = copy.deepcopy(entities)

    def get_source(self, organization_id: str, source_id: str, *, with_file: bool = False) -> CadSourceRecord | None:
        record = self._sources.get((organization_id, source_id))
        if record is None:
            return None
        return copy.deepcopy(record if with_file else replace(record, file_data=None))

    def list_entities(self, organization_id: str, source_id: str) -> list[CadEntity]:
        return copy.deepcopy(self._entities.get((organization_id, source_id), []))

    def replace_entities(
        self,
        organization_id: str,
        source_id: str,
        entities: list[CadEntity],
        params: dict[str, Any],
        summary: dict[str, Any],
    ) -> None:
        record = self._require(organization_id, source_id)
        record.params = copy.deepcopy(params)
        record.summary = copy.deepcopy(summary)
        self._entities[(organization_id, source_id)] = copy.deepcopy(entities)

    def update_roles(
        self,
        organization_id: str,
        source_id: str,
        roles: dict[str, tuple[str, str]],
        summary: dict[str, Any],
    ) -> None:
        record = self._require(organization_id, source_id)
        for item in self._entities.get((organization_id, source_id), []):
            if item.handle in roles:
                item.role, item.role_origin = roles[item.handle]
        record.summary = copy.deepcopy(summary)

    def get_layer_template(self, organization_id: str, site_code: str) -> dict[str, TemplateEntry]:
        return {key: entry for key, (_, entry) in self._templates.get((organization_id, site_code), {}).items()}

    def add_missing_layer_roles(self, organization_id: str, site_code: str, roles: dict[str, str], actor: str) -> None:
        template = self._templates.setdefault((organization_id, site_code), {})
        for key, (name, role) in _template_rows(roles).items():
            template.setdefault(key, (name, TemplateEntry(role)))

    def upsert_layer_roles(self, organization_id: str, site_code: str, roles: dict[str, str], actor: str) -> None:
        template = self._templates.setdefault((organization_id, site_code), {})
        for key, (name, role) in _template_rows(roles).items():
            template[key] = (name, TemplateEntry(role, manual=True))

    def _require(self, organization_id: str, source_id: str) -> CadSourceRecord:
        record = self._sources.get((organization_id, source_id))
        if record is None:
            raise CadSourceNotFound(source_id)
        return record
