<<<<<<< Updated upstream
FROM python:3.11-slim-bookworm AS runtime
=======
FROM python:3.11.11-slim-bookworm AS runtime
>>>>>>> Stashed changes

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

RUN groupadd --system --gid 10001 fugu \
    && useradd --system --uid 10001 --gid fugu --home-dir /app --shell /usr/sbin/nologin fugu

WORKDIR /app

COPY requirements-runtime.txt ./requirements-runtime.txt
RUN python -m pip install --upgrade "pip==26.1.1" \
    && python -m pip install --requirement requirements-runtime.txt

COPY pyproject.toml ./pyproject.toml
COPY src ./src
RUN python -m pip install --no-deps .

COPY alembic.ini ./alembic.ini
COPY alembic ./alembic
COPY entrypoint.sh ./entrypoint.sh
RUN chmod 0555 /app/entrypoint.sh \
    && chown -R fugu:fugu /app

USER 10001:10001

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health/live', timeout=3).read()"

ENTRYPOINT ["/app/entrypoint.sh"]
