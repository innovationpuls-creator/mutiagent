# syntax=docker/dockerfile:1.7

FROM python:3.12-slim-bookworm AS runtime

ARG DEBIAN_MIRROR=http://deb.debian.org/debian
ARG DEBIAN_SECURITY_MIRROR=http://deb.debian.org/debian-security
ARG PGDG_KEY_URL=https://www.postgresql.org/media/keys/ACCC4CF8.asc
ARG PGDG_REPOSITORY="deb [signed-by=/usr/share/postgresql-common/pgdg/apt.postgresql.org.asc] https://apt.postgresql.org/pub/repos/apt bookworm-pgdg main"
ARG PYTHON_PACKAGE_INDEX=https://pypi.org/simple
ARG UV_HTTP_TIMEOUT=300

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    VIRTUAL_ENV=/opt/venv \
    PATH=/opt/venv/bin:/usr/local/bin:/usr/bin:/bin \
    PYTHONPATH=/opt/onetree/backend

RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt/lists,sharing=locked \
    sed -i \
        -e "s|http://deb.debian.org/debian-security|$DEBIAN_SECURITY_MIRROR|g" \
        -e "s|http://deb.debian.org/debian|$DEBIAN_MIRROR|g" \
        /etc/apt/sources.list.d/debian.sources \
    && apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl git \
    && install -d -m 0755 /usr/share/postgresql-common/pgdg \
    && curl --fail --silent --show-error --location "$PGDG_KEY_URL" \
        --output /usr/share/postgresql-common/pgdg/apt.postgresql.org.asc \
    && printf '%s\n' "$PGDG_REPOSITORY" \
        > /etc/apt/sources.list.d/pgdg.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends postgresql-client-18

RUN --mount=type=cache,target=/root/.cache/pip,sharing=locked \
    PIP_DEFAULT_TIMEOUT="$UV_HTTP_TIMEOUT" \
    python -m pip install --index-url "$PYTHON_PACKAGE_INDEX" uv==0.8.22

WORKDIR /opt/onetree/backend
COPY backend/pyproject.toml backend/uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv,sharing=locked \
    UV_HTTP_TIMEOUT="$UV_HTTP_TIMEOUT" \
    uv sync --frozen --no-dev --no-install-project \
    --default-index "$PYTHON_PACKAGE_INDEX"

COPY backend/ ./
COPY deploy/ /opt/onetree/deploy/
RUN --mount=type=cache,target=/root/.cache/uv,sharing=locked \
    UV_HTTP_TIMEOUT="$UV_HTTP_TIMEOUT" \
    uv sync --frozen --no-dev --default-index "$PYTHON_PACKAGE_INDEX" \
    && /usr/sbin/groupadd --gid 10001 onetree \
    && /usr/sbin/useradd --uid 10001 --gid onetree --create-home onetree \
    && install -d -o onetree -g onetree -m 0750 \
        /var/lib/onetree/knowledge-base-uploads \
    && chown -R onetree:onetree /opt/onetree /opt/venv

USER onetree
EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
