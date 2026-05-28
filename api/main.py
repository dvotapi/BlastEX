"""Точка входа FastAPI для BlastEX REST API."""
from __future__ import annotations

import os
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from api.exceptions import BlastExError
from api.routers import blast, cost, references

API_PREFIX = "/api/v1"

app = FastAPI(
    title="BlastEX API",
    description=(
        "REST API технологических расчётов БВР и сметных стратегий BlastEX. "
        "Изолирует `BlastEngine` и `CostEngine` от Streamlit UI."
    ),
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
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


@app.get("/health", tags=["system"])
def healthcheck() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/", tags=["system"])
def root() -> dict[str, str]:
    return {"service": "BlastEX API", "docs": "/docs", "api_prefix": API_PREFIX}


app.include_router(references.router, prefix=API_PREFIX)
app.include_router(blast.router, prefix=API_PREFIX)
app.include_router(cost.router, prefix=API_PREFIX)
