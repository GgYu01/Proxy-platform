# Mainland mirrors keep base-image, apt, and pip pulls on fast paths.
ARG PYTHON_BASE_IMAGE=docker.m.daocloud.io/library/python:3.12.8-slim-bookworm
ARG PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple
ARG PIP_TRUSTED_HOST=mirrors.aliyun.com
ARG APT_MIRROR_URL=https://mirrors.aliyun.com

FROM ${PYTHON_BASE_IMAGE} AS builder

ARG PIP_INDEX_URL
ARG PIP_TRUSTED_HOST

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_INDEX_URL=${PIP_INDEX_URL} \
    PIP_TRUSTED_HOST=${PIP_TRUSTED_HOST} \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /build

COPY pyproject.toml README.md ./
COPY src ./src

RUN python -m pip wheel --wheel-dir /tmp/wheels .


FROM ${PYTHON_BASE_IMAGE}

ARG PIP_INDEX_URL
ARG PIP_TRUSTED_HOST
ARG APT_MIRROR_URL

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_INDEX_URL=${PIP_INDEX_URL} \
    PIP_TRUSTED_HOST=${PIP_TRUSTED_HOST} \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN printf '%s\n' \
      "deb ${APT_MIRROR_URL}/debian bookworm main" \
      "deb ${APT_MIRROR_URL}/debian-security bookworm-security main" \
      > /etc/apt/sources.list \
    && rm -f /etc/apt/sources.list.d/debian.sources \
    && apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY --from=builder /tmp/wheels /tmp/wheels
RUN python -m pip install /tmp/wheels/*.whl && rm -rf /tmp/wheels

COPY platform.manifest.yaml ./platform.manifest.yaml

CMD ["python", "-m", "proxy_platform.deploy_runtime"]
