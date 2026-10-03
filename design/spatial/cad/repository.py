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
    func,
    insert,
    select,
    update,
)
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Mapped, deferred, mapped_column, sessionmaker

from cost.v2.db_repository import SCHEMA, Base, JsonType
from design.spatial.cad.model import DEFAULT_AREA_BASIS, ROLE_SITUATION, CadEntity
from design.spatial.cad.roles import TemplateEntry, layer_key


class CadSourceNotFound(LookupError):
    """Источника нет в этой организации."""


class CadSourceConflict(RuntimeError):
    """Источник изменили после того, как его прочитали: запись с устаревшей ревизией."""


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
    # Название источника (PR 4): источники объекта с одинаковым названием —
    # версии одной серии ситуации.
    title: str = ""
    survey_date: date | None = None
    coordinate_system: dict[str, Any] | None = None
    file_data: bytes | None = field(default=None, repr=False)
    # Номер правки: запись роли или разбора проходит, только если он не сменился.
    revision: int = 1


class CadRepository(Protocol):
    def create_sources(
        self, organization_id: str, items: list[tuple[CadSourceRecord, list[CadEntity]]]
    ) -> None: ...

    def get_source(self, organization_id: str, source_id: str, *, with_file: bool = False) -> CadSourceRecord | None: ...

    def list_entities(
        self,
        organization_id: str,
        source_id: str,
        *,
        roles: set[str] | None = None,
        handles: set[str] | None = None,
    ) -> list[CadEntity]: ...

    def replace_entities(
        self,
        organization_id: str,
        source_id: str,
        entities: list[CadEntity],
        params: dict[str, Any],
        summary: dict[str, Any],
        *,
        expected_revision: int,
    ) -> None: ...

    def update_roles(
        self,
        organization_id: str,
        source_id: str,
        roles: dict[str, tuple[str, str]],
        summary: dict[str, Any],
        *,
        expected_revision: int,
    ) -> None: ...

    def get_layer_template(self, organization_id: str, site_code: str) -> dict[str, TemplateEntry]: ...

    def add_missing_layer_roles(self, organization_id: str, site_code: str, roles: dict[str, str], actor: str) -> None: ...

    def upsert_layer_roles(self, organization_id: str, site_code: str, roles: dict[str, str], actor: str) -> None: ...

    def get_area_basis(self, organization_id: str, site_code: str) -> str | None: ...

    def set_area_basis(self, organization_id: str, site_code: str, area_basis: str, actor: str) -> None: ...

    def find_source_by_sha(self, organization_id: str, site_code: str, sha256: str) -> CadSourceRecord | None: ...

    def list_site_sources(self, organization_id: str, site_code: str, *, limit: int) -> list[CadSourceRecord]: ...

    def update_source_meta(
        self,
        organization_id: str,
        source_id: str,
        *,
        title: str,
        survey_date: date | None,
        expected_revision: int,
    ) -> None: ...

    def delete_source(self, organization_id: str, source_id: str) -> None: ...

    def get_site_crs(self, organization_id: str, site_code: str) -> dict[str, Any] | None: ...

    def set_site_crs(self, organization_id: str, site_code: str, crs: dict[str, Any], actor: str) -> None: ...

    def count_entities_by_role(self, organization_id: str, source_ids: set[str], role: str) -> dict[str, int]: ...

    def list_situation_sources(
        self, organization_id: str, site_code: str, *, limit: int
    ) -> list[tuple[CadSourceRecord, int]]: ...

    def upsert_layer_kinds(
        self, organization_id: str, site_code: str, kinds: dict[str, str | None], actor: str
    ) -> None: ...


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
        Index("ix_cad_sources_org_site_sha", "organization_id", "site_code", "file_sha256"),
        {"schema": SCHEMA},
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    organization_id: Mapped[str] = mapped_column(String(120), nullable=False)
    site_code: Mapped[str] = mapped_column(String(80), nullable=False, default="")
    work_object_name: Mapped[str] = mapped_column(String(300), nullable=False, default="")
    file_name: Mapped[str] = mapped_column(String(300), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False, default="")
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
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


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
    # Вид объекта ситуации, заданный человеком; NULL — по имени слоя.
    situation_kind: Mapped[str | None] = mapped_column(String(16), nullable=True)
    updated_by: Mapped[str] = mapped_column(String(320), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class CadSiteSettingsRow(Base):
    """Настройки объекта для импорта чертежа: площадь блока и система координат."""

    __tablename__ = "cad_site_settings"
    __table_args__ = ({"schema": SCHEMA},)

    organization_id: Mapped[str] = mapped_column(String(120), primary_key=True)
    site_code: Mapped[str] = mapped_column(String(80), primary_key=True)
    area_basis: Mapped[str] = mapped_column(String(16), nullable=False, default=DEFAULT_AREA_BASIS)
    # СК объекта (PR 4): «МСК-66 зона 1», высоты «Балтийская 1977», EPSG — если есть.
    crs_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    height_system: Mapped[str | None] = mapped_column(String(120), nullable=True)
    epsg: Mapped[int | None] = mapped_column(Integer, nullable=True)
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


def _record(row: CadSourceRow, *, with_file: bool = False) -> CadSourceRecord:
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
        title=row.title,
        survey_date=row.survey_date,
        coordinate_system=row.coordinate_system,
        file_data=bytes(row.file_data) if with_file else None,
        revision=row.revision,
    )


def _crs(row: CadSiteSettingsRow) -> dict[str, Any] | None:
    if row.crs_name is None and row.height_system is None and row.epsg is None:
        return None
    return {"name": row.crs_name or "", "height_system": row.height_system or "", "epsg": row.epsg}


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
                        title=record.title,
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
            return None if row is None else _record(row, with_file=with_file)

    def list_entities(
        self,
        organization_id: str,
        source_id: str,
        *,
        roles: set[str] | None = None,
        handles: set[str] | None = None,
    ) -> list[CadEntity]:
        # Контур читает только линии нужных ролей: на чертеже карьера объектов
        # десятки тысяч, а предпросмотр контура зовётся на каждое действие.
        if roles is not None and not roles or handles is not None and not handles:
            return []
        query = select(CadEntityRow).where(
            CadEntityRow.organization_id == organization_id, CadEntityRow.source_id == source_id
        )
        if roles is not None:
            query = query.where(CadEntityRow.role.in_(sorted(roles)))
        if handles is not None:
            query = query.where(CadEntityRow.handle.in_(sorted(handles)))
        with self.session_factory() as session:
            rows = session.execute(query.order_by(CadEntityRow.seq)).scalars()
            return [_entity(row) for row in rows]

    def replace_entities(
        self,
        organization_id: str,
        source_id: str,
        entities: list[CadEntity],
        params: dict[str, Any],
        summary: dict[str, Any],
        *,
        expected_revision: int,
    ) -> None:
        with self.session_factory() as session, session.begin():
            self._bump(session, organization_id, source_id, expected_revision, params=params, summary=summary)
            session.execute(
                delete(CadEntityRow).where(
                    CadEntityRow.organization_id == organization_id, CadEntityRow.source_id == source_id
                )
            )
            if entities:
                session.execute(insert(CadEntityRow), _entity_rows(organization_id, source_id, entities))

    def update_roles(
        self,
        organization_id: str,
        source_id: str,
        roles: dict[str, tuple[str, str]],
        summary: dict[str, Any],
        *,
        expected_revision: int,
    ) -> None:
        with self.session_factory() as session, session.begin():
            self._bump(session, organization_id, source_id, expected_revision, summary=summary)
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

    def get_layer_template(self, organization_id: str, site_code: str) -> dict[str, TemplateEntry]:
        with self.session_factory() as session:
            rows = session.execute(
                select(CadLayerRoleRow).where(
                    CadLayerRoleRow.organization_id == organization_id, CadLayerRoleRow.site_code == site_code
                )
            ).scalars()
            return {row.layer_key: TemplateEntry(row.role, row.manual, row.situation_kind) for row in rows}

    def add_missing_layer_roles(self, organization_id: str, site_code: str, roles: dict[str, str], actor: str) -> None:
        self._write_template(organization_id, site_code, roles, actor, overwrite=False)

    def upsert_layer_roles(self, organization_id: str, site_code: str, roles: dict[str, str], actor: str) -> None:
        self._write_template(organization_id, site_code, roles, actor, overwrite=True)

    def get_area_basis(self, organization_id: str, site_code: str) -> str | None:
        with self.session_factory() as session:
            return session.execute(
                select(CadSiteSettingsRow.area_basis).where(
                    CadSiteSettingsRow.organization_id == organization_id, CadSiteSettingsRow.site_code == site_code
                )
            ).scalar_one_or_none()

    def set_area_basis(self, organization_id: str, site_code: str, area_basis: str, actor: str) -> None:
        values = {
            "organization_id": organization_id,
            "site_code": site_code,
            "area_basis": area_basis,
            "updated_by": actor,
            "updated_at": _now(),
        }
        statement = pg_insert(CadSiteSettingsRow).values(values).on_conflict_do_update(
            index_elements=[CadSiteSettingsRow.organization_id, CadSiteSettingsRow.site_code],
            set_={"area_basis": area_basis, "updated_by": actor, "updated_at": values["updated_at"]},
        )
        with self.session_factory() as session, session.begin():
            session.execute(statement)

    def find_source_by_sha(self, organization_id: str, site_code: str, sha256: str) -> CadSourceRecord | None:
        with self.session_factory() as session:
            row = session.execute(
                select(CadSourceRow)
                .where(
                    CadSourceRow.organization_id == organization_id,
                    CadSourceRow.site_code == site_code,
                    CadSourceRow.file_sha256 == sha256,
                )
                .order_by(CadSourceRow.uploaded_at.desc())
                .limit(1)
            ).scalar_one_or_none()
            return None if row is None else _record(row)

    def list_site_sources(self, organization_id: str, site_code: str, *, limit: int) -> list[CadSourceRecord]:
        with self.session_factory() as session:
            rows = session.execute(
                select(CadSourceRow)
                .where(CadSourceRow.organization_id == organization_id, CadSourceRow.site_code == site_code)
                .order_by(CadSourceRow.uploaded_at.desc(), CadSourceRow.id)
                .limit(limit)
            ).scalars()
            return [_record(row) for row in rows]

    def update_source_meta(
        self,
        organization_id: str,
        source_id: str,
        *,
        title: str,
        survey_date: date | None,
        expected_revision: int,
    ) -> None:
        with self.session_factory() as session, session.begin():
            self._bump(session, organization_id, source_id, expected_revision, title=title, survey_date=survey_date)

    def delete_source(self, organization_id: str, source_id: str) -> None:
        # Сущности уходят каскадом (FK ondelete=CASCADE).
        with self.session_factory() as session, session.begin():
            result = session.execute(
                delete(CadSourceRow).where(
                    CadSourceRow.organization_id == organization_id, CadSourceRow.id == source_id
                )
            )
            if result.rowcount == 0:
                raise CadSourceNotFound(source_id)

    def get_site_crs(self, organization_id: str, site_code: str) -> dict[str, Any] | None:
        with self.session_factory() as session:
            row = session.execute(
                select(CadSiteSettingsRow).where(
                    CadSiteSettingsRow.organization_id == organization_id, CadSiteSettingsRow.site_code == site_code
                )
            ).scalar_one_or_none()
            return None if row is None else _crs(row)

    def set_site_crs(self, organization_id: str, site_code: str, crs: dict[str, Any], actor: str) -> None:
        columns = {
            "crs_name": crs.get("name") or "",
            "height_system": crs.get("height_system") or "",
            "epsg": crs.get("epsg"),
            "updated_by": actor,
            "updated_at": _now(),
        }
        statement = pg_insert(CadSiteSettingsRow).values(
            {"organization_id": organization_id, "site_code": site_code, "area_basis": DEFAULT_AREA_BASIS, **columns}
        )
        statement = statement.on_conflict_do_update(
            index_elements=[CadSiteSettingsRow.organization_id, CadSiteSettingsRow.site_code], set_=columns
        )
        with self.session_factory() as session, session.begin():
            session.execute(statement)

    def count_entities_by_role(self, organization_id: str, source_ids: set[str], role: str) -> dict[str, int]:
        if not source_ids:
            return {}
        with self.session_factory() as session:
            rows = session.execute(
                select(CadEntityRow.source_id, func.count())
                .where(
                    CadEntityRow.organization_id == organization_id,
                    CadEntityRow.source_id.in_(sorted(source_ids)),
                    CadEntityRow.role == role,
                )
                .group_by(CadEntityRow.source_id)
            ).all()
            return {source_id: int(count) for source_id, count in rows}

    def list_situation_sources(
        self, organization_id: str, site_code: str, *, limit: int
    ) -> list[tuple[CadSourceRecord, int]]:
        """Источники объекта, где есть объекты ситуации, свежие первыми, и их число.

        Сводка, параметры и байты файла не читаются: каталогу нужны только
        название, даты и ревизия, а файлов блоков без ситуации у объекта сотни.
        """

        counts = (
            select(CadEntityRow.source_id, func.count().label("situation_count"))
            .where(CadEntityRow.organization_id == organization_id, CadEntityRow.role == ROLE_SITUATION)
            .group_by(CadEntityRow.source_id)
            .subquery()
        )
        query = (
            select(
                CadSourceRow.id,
                CadSourceRow.site_code,
                CadSourceRow.work_object_name,
                CadSourceRow.file_name,
                CadSourceRow.title,
                CadSourceRow.file_format,
                CadSourceRow.file_size,
                CadSourceRow.file_sha256,
                CadSourceRow.uploaded_by,
                CadSourceRow.uploaded_at,
                CadSourceRow.survey_date,
                CadSourceRow.revision,
                counts.c.situation_count,
            )
            .join(counts, counts.c.source_id == CadSourceRow.id)
            .where(CadSourceRow.organization_id == organization_id, CadSourceRow.site_code == site_code)
            .order_by(CadSourceRow.uploaded_at.desc(), CadSourceRow.id)
            .limit(limit)
        )
        with self.session_factory() as session:
            rows = session.execute(query).all()
        return [
            (
                CadSourceRecord(
                    id=row.id,
                    site_code=row.site_code,
                    work_object_name=row.work_object_name,
                    file_name=row.file_name,
                    file_format=row.file_format,
                    file_size=row.file_size,
                    file_sha256=row.file_sha256,
                    params={},
                    summary={},
                    uploaded_by=row.uploaded_by,
                    uploaded_at=row.uploaded_at,
                    title=row.title,
                    survey_date=row.survey_date,
                    revision=row.revision,
                ),
                int(row.situation_count),
            )
            for row in rows
        ]

    def upsert_layer_kinds(
        self, organization_id: str, site_code: str, kinds: dict[str, str | None], actor: str
    ) -> None:
        rows = [
            {
                "organization_id": organization_id,
                "site_code": site_code,
                "layer_key": layer_key(name),
                "layer_name": name,
                # Слоя ещё нет в шаблоне — вид задают только слою ситуации.
                "role": ROLE_SITUATION,
                "manual": False,
                "situation_kind": kind,
                "updated_by": actor,
                "updated_at": _now(),
            }
            for name, kind in kinds.items()
            if layer_key(name)
        ]
        if not rows:
            return
        statement = pg_insert(CadLayerRoleRow).values(rows)
        statement = statement.on_conflict_do_update(
            index_elements=[CadLayerRoleRow.organization_id, CadLayerRoleRow.site_code, CadLayerRoleRow.layer_key],
            set_={
                "situation_kind": statement.excluded.situation_kind,
                "updated_by": statement.excluded.updated_by,
                "updated_at": statement.excluded.updated_at,
            },
        )
        with self.session_factory() as session, session.begin():
            session.execute(statement)

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

    @classmethod
    def _bump(cls, session, organization_id: str, source_id: str, expected_revision: int, **values: Any) -> None:
        """Обновляет источник и ревизию, если её никто не сменил с момента чтения.

        Проверка и запись — один UPDATE: параллельная транзакция ждёт блокировку
        строки и после неё уже не находит прежнюю ревизию.
        """

        result = session.execute(
            update(CadSourceRow)
            .where(
                CadSourceRow.organization_id == organization_id,
                CadSourceRow.id == source_id,
                CadSourceRow.revision == expected_revision,
            )
            .values(revision=CadSourceRow.revision + 1, **values)
        )
        if result.rowcount == 0:
            cls._require(session, organization_id, source_id)
            raise CadSourceConflict(source_id)

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
        self._area_bases: dict[tuple[str, str], str] = {}
        self._crs: dict[tuple[str, str], dict[str, Any]] = {}

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

    def list_entities(
        self,
        organization_id: str,
        source_id: str,
        *,
        roles: set[str] | None = None,
        handles: set[str] | None = None,
    ) -> list[CadEntity]:
        return copy.deepcopy(
            [
                item
                for item in self._entities.get((organization_id, source_id), [])
                if (roles is None or item.role in roles) and (handles is None or item.handle in handles)
            ]
        )

    def replace_entities(
        self,
        organization_id: str,
        source_id: str,
        entities: list[CadEntity],
        params: dict[str, Any],
        summary: dict[str, Any],
        *,
        expected_revision: int,
    ) -> None:
        record = self._bump(organization_id, source_id, expected_revision)
        record.params = copy.deepcopy(params)
        record.summary = copy.deepcopy(summary)
        self._entities[(organization_id, source_id)] = copy.deepcopy(entities)

    def update_roles(
        self,
        organization_id: str,
        source_id: str,
        roles: dict[str, tuple[str, str]],
        summary: dict[str, Any],
        *,
        expected_revision: int,
    ) -> None:
        record = self._bump(organization_id, source_id, expected_revision)
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
            kind = template[key][1].kind if key in template else None
            template[key] = (name, TemplateEntry(role, manual=True, kind=kind))

    def get_area_basis(self, organization_id: str, site_code: str) -> str | None:
        return self._area_bases.get((organization_id, site_code))

    def set_area_basis(self, organization_id: str, site_code: str, area_basis: str, actor: str) -> None:
        self._area_bases[(organization_id, site_code)] = area_basis

    def find_source_by_sha(self, organization_id: str, site_code: str, sha256: str) -> CadSourceRecord | None:
        found = [
            record
            for (org, _), record in self._sources.items()
            if org == organization_id and record.site_code == site_code and record.file_sha256 == sha256
        ]
        if not found:
            return None
        return copy.deepcopy(replace(max(found, key=lambda item: item.uploaded_at), file_data=None))

    def list_site_sources(self, organization_id: str, site_code: str, *, limit: int) -> list[CadSourceRecord]:
        found = [
            record
            for (org, _), record in self._sources.items()
            if org == organization_id and record.site_code == site_code
        ]
        found.sort(key=lambda item: item.id)
        found.sort(key=lambda item: item.uploaded_at, reverse=True)
        return [copy.deepcopy(replace(item, file_data=None)) for item in found[:limit]]

    def update_source_meta(
        self,
        organization_id: str,
        source_id: str,
        *,
        title: str,
        survey_date: date | None,
        expected_revision: int,
    ) -> None:
        record = self._bump(organization_id, source_id, expected_revision)
        record.title, record.survey_date = title, survey_date

    def delete_source(self, organization_id: str, source_id: str) -> None:
        self._require(organization_id, source_id)
        del self._sources[(organization_id, source_id)]
        self._entities.pop((organization_id, source_id), None)

    def get_site_crs(self, organization_id: str, site_code: str) -> dict[str, Any] | None:
        crs = self._crs.get((organization_id, site_code))
        return copy.deepcopy(crs) if crs is not None else None

    def set_site_crs(self, organization_id: str, site_code: str, crs: dict[str, Any], actor: str) -> None:
        self._crs[(organization_id, site_code)] = {
            "name": crs.get("name") or "",
            "height_system": crs.get("height_system") or "",
            "epsg": crs.get("epsg"),
        }

    def count_entities_by_role(self, organization_id: str, source_ids: set[str], role: str) -> dict[str, int]:
        counts: dict[str, int] = {}
        for source_id in source_ids:
            count = sum(1 for item in self._entities.get((organization_id, source_id), []) if item.role == role)
            if count:
                counts[source_id] = count
        return counts

    def list_situation_sources(
        self, organization_id: str, site_code: str, *, limit: int
    ) -> list[tuple[CadSourceRecord, int]]:
        found: list[tuple[CadSourceRecord, int]] = []
        for (org, source_id), record in self._sources.items():
            if org != organization_id or record.site_code != site_code:
                continue
            count = sum(1 for item in self._entities.get((org, source_id), []) if item.role == ROLE_SITUATION)
            if count:
                found.append((replace(record, file_data=None, params={}, summary={}), count))
        found.sort(key=lambda item: item[0].id)
        found.sort(key=lambda item: item[0].uploaded_at, reverse=True)
        return copy.deepcopy(found[:limit])

    def upsert_layer_kinds(
        self, organization_id: str, site_code: str, kinds: dict[str, str | None], actor: str
    ) -> None:
        template = self._templates.setdefault((organization_id, site_code), {})
        for name, kind in kinds.items():
            key = layer_key(name)
            if not key:
                continue
            stored_name, entry = template.get(key, (name, TemplateEntry(ROLE_SITUATION)))
            template[key] = (stored_name, replace(entry, kind=kind))

    def _require(self, organization_id: str, source_id: str) -> CadSourceRecord:
        record = self._sources.get((organization_id, source_id))
        if record is None:
            raise CadSourceNotFound(source_id)
        return record

    def _bump(self, organization_id: str, source_id: str, expected_revision: int) -> CadSourceRecord:
        record = self._require(organization_id, source_id)
        if record.revision != expected_revision:
            raise CadSourceConflict(source_id)
        record.revision += 1
        return record
