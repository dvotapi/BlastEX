# syntax=docker/dockerfile:1

FROM python:3.11-slim AS builder

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# Чтение DWG: GNU LibreDWG даёт утилиту dwg2dxf. В репозиториях Debian её нет,
# поэтому собираем из релизного архива. Лицензия GPL-3: утилита вызывается
# отдельным процессом, на код BlastEX лицензия не распространяется.
FROM python:3.11-slim AS dwg-builder

ARG LIBREDWG_VERSION=0.14

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential curl ca-certificates pkg-config libpcre2-dev \
    && rm -rf /var/lib/apt/lists/*

RUN set -eux; \
    curl -fsSL "https://github.com/LibreDWG/libredwg/releases/download/${LIBREDWG_VERSION}/libredwg-${LIBREDWG_VERSION}.tar.gz" -o /tmp/libredwg.tar.gz; \
    mkdir -p /tmp/libredwg && tar -xzf /tmp/libredwg.tar.gz -C /tmp/libredwg --strip-components=1; \
    cd /tmp/libredwg; \
    ./configure --disable-bindings --disable-docs --disable-shared --prefix=/opt/libredwg; \
    make -j"$(nproc)"; \
    make install; \
    rm -rf /tmp/libredwg /tmp/libredwg.tar.gz

FROM python:3.11-slim AS runtime

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    MPLCONFIGDIR=/tmp/matplotlib

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/* \
    && adduser --disabled-password --gecos "" appuser

COPY --from=dwg-builder /opt/libredwg/bin/dwg2dxf /usr/local/bin/dwg2dxf

COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

COPY Blast.py blast_hole.py blast_hole_viz.py ./
COPY cost/ ./cost/
COPY design/ ./design/
COPY simulation/ ./simulation/
COPY intelligence/ ./intelligence/
COPY api/ ./api/
COPY alembic.ini ./
COPY migrations/ ./migrations/
COPY scripts/start_api.py ./scripts/start_api.py

RUN mkdir -p /app/data/teams /app/data/mass_blast_documents /app/data/mass_blast_attachments \
    && chown -R appuser:appuser /app/data

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["python", "scripts/start_api.py"]
