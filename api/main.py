"""Точка входа FastAPI для BlastEX REST API."""
from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

import matplotlib

matplotlib.use("Agg")  # без дисплея в контейнере — до любого импорта pyplot

from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from api import config
from api.exceptions import BlastExError
from api.routers import auth, blast, cost, calibration, datasets, design, drift, economics, learning, mass_blast, optimization, outcomes, recommendation, references, registry, scenarios, spatial, workspace
from api.security import require_internal_access

API_PREFIX = "/api/v1"

@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    """Проверка окружения до первого запроса.

    Хранилище одно — PostgreSQL. Без строки подключения приложение должно не
    стартовать, а не отдавать 503 на половине маршрутов.
    """

    config.database_url()
    yield


app = FastAPI(
    title="BlastEX API",
    description=(
        "REST API технологических расчётов БВР и экономики BlastEX. "
        "Хранилище — PostgreSQL (схема blastex)."
    ),
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

_cors_origins = os.getenv("BLASTEX_CORS_ORIGINS", "*")
allow_origins = (
    ["*"] if _cors_origins.strip() == "*" else [o.strip() for o in _cors_origins.split(",")]
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _error_payload(
    *,
    message: str,
    error_type: str,
    status_code: int,
    details: Any = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "detail": message,
        "error_type": error_type,
        "status_code": status_code,
    }
    if details is not None:
        payload["details"] = details
    return payload


@app.exception_handler(BlastExError)
async def blastex_error_handler(_: Request, exc: BlastExError) -> JSONResponse:
    return JSONResponse(
        status_code=400,
        content=_error_payload(
            message=exc.message,
            error_type=exc.error_type,
            status_code=400,
        ),
    )


@app.exception_handler(ValueError)
async def value_error_handler(_: Request, exc: ValueError) -> JSONResponse:
    return JSONResponse(
        status_code=400,
        content=_error_payload(
            message=str(exc),
            error_type="value_error",
            status_code=400,
        ),
    )


@app.exception_handler(ZeroDivisionError)
async def zero_division_handler(_: Request, exc: ZeroDivisionError) -> JSONResponse:
    return JSONResponse(
        status_code=400,
        content=_error_payload(
            message="Деление на ноль при расчёте. Проверьте геометрию блока и входные параметры.",
            error_type="division_by_zero",
            status_code=400,
            details=str(exc),
        ),
    )


@app.exception_handler(RequestValidationError)
async def request_validation_handler(
    _: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content=_error_payload(
            message="Ошибка валидации входных данных.",
            error_type="validation_error",
            status_code=422,
            details=exc.errors(),
        ),
    )


@app.exception_handler(ValidationError)
async def pydantic_validation_handler(_: Request, exc: ValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content=_error_payload(
            message="Ошибка сериализации ответа.",
            error_type="response_validation_error",
            status_code=422,
            details=exc.errors(),
        ),
    )


@app.get("/api/v1/features", tags=["system"])
def features() -> dict[str, bool]:
    """Какие модули включены в этой установке."""

    return config.features()


@app.get("/health", tags=["system"])
def healthcheck() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/", tags=["system"])
def root() -> dict[str, str]:
    return {"service": "BlastEX API", "docs": "/docs", "api_prefix": API_PREFIX}


app.include_router(auth.router, prefix=API_PREFIX)
_internal_dependencies = [Depends(require_internal_access)]
app.include_router(references.router, prefix=API_PREFIX, dependencies=_internal_dependencies)
app.include_router(blast.router, prefix=API_PREFIX, dependencies=_internal_dependencies)
app.include_router(cost.router, prefix=API_PREFIX, dependencies=_internal_dependencies)
app.include_router(economics.router, prefix=API_PREFIX, dependencies=_internal_dependencies)
app.include_router(design.router, prefix=API_PREFIX, dependencies=_internal_dependencies)
app.include_router(mass_blast.router, prefix=API_PREFIX, dependencies=_internal_dependencies)
app.include_router(scenarios.router, prefix=API_PREFIX, dependencies=_internal_dependencies)
app.include_router(workspace.router, prefix=API_PREFIX, dependencies=_internal_dependencies)

# ML-слой не входит в ближайший релиз. Код `intelligence/` и
# `design/optimization` остаётся на месте, но включается переменной
# BLASTEX_INTELLIGENCE_ENABLED, а не правкой кода.
_INTELLIGENCE_ROUTERS = (
    datasets.router,
    calibration.router,
    outcomes.router,
    optimization.router,
    recommendation.router,
    learning.router,
    registry.router,
    drift.router,
    spatial.router,
)

if config.intelligence_enabled():
    for _router in _INTELLIGENCE_ROUTERS:
        app.include_router(_router, prefix=API_PREFIX, dependencies=_internal_dependencies)
else:

    def _module_disabled(_: str = "") -> JSONResponse:
        return JSONResponse(
            status_code=501,
            content=_error_payload(
                message=(
                    "Модуль отключён. Включите его переменной "
                    f"{config.INTELLIGENCE_ENABLED_ENV}=true."
                ),
                error_type="module_disabled",
                status_code=501,
            ),
        )

    # Пути отключённых роутеров повторяются один в один: часть ML-слоя живёт
    # под общим префиксом /design, где остальные маршруты продолжают работать.
    _disabled_paths: dict[str, set[str]] = {}
    for _router in _INTELLIGENCE_ROUTERS:
        for _route in _router.routes:
            _disabled_paths.setdefault(f"{API_PREFIX}{_route.path}", set()).update(
                getattr(_route, "methods", {"GET"})
            )
    for _prefix in config.INTELLIGENCE_PREFIXES:
        if _prefix in {"optimization", "recommendation"}:
            continue
        _disabled_paths.setdefault(f"{API_PREFIX}/{_prefix}", set()).update(
            {"GET", "POST", "PUT", "PATCH", "DELETE"}
        )
        _disabled_paths[f"{API_PREFIX}/{_prefix}/{{path:path}}"] = {
            "GET", "POST", "PUT", "PATCH", "DELETE"
        }
    for _index, (_path, _methods) in enumerate(sorted(_disabled_paths.items())):
        app.add_api_route(
            _path,
            _module_disabled,
            methods=sorted(_methods - {"HEAD", "OPTIONS"}) or ["GET"],
            include_in_schema=False,
            name=f"module_disabled_{_index}",
        )
