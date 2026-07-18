# Stage 1: Build with all dependencies
FROM python:3.14-slim-trixie@sha256:d3400aa122fa42cf0af0dbe8ec3091b047eac5c8f7e3539f7135e86d855dc015 AS builder

ARG APP_HOME=/app
WORKDIR ${APP_HOME}

# Do not create .pyc files, unbuffered logs
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    DEBIAN_FRONTEND=noninteractive

# Install system dependencies.
# hadolint ignore=DL3008
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    ca-certificates \
    curl \
    libpq-dev \
 && apt-get clean \
 && rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

# Copy and install Python dependencies
COPY ./gps_layer/requirements.lock ./
RUN pip install --prefix=/install --no-cache-dir --require-hashes --only-binary :all: -r requirements.lock \
 && find /install -name "*.pyc" -delete \
 && find /install -depth -type d -name "__pycache__" -exec rm -rf {} +

# Stage 2: Lightweight runtime image
FROM python:3.14-slim-trixie@sha256:d3400aa122fa42cf0af0dbe8ec3091b047eac5c8f7e3539f7135e86d855dc015 AS runtime

ARG APP_HOME=/app
WORKDIR ${APP_HOME}

COPY --from=builder /install /usr/local

ENV DEBIAN_FRONTEND=noninteractive

# hadolint ignore=DL3008
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    libpq-dev \
 && apt-get clean \
 && rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/* \
 && groupadd --gid 10001 appuser \
 && useradd --uid 10001 --gid appuser --create-home --shell /usr/sbin/nologin appuser \
 && mkdir -p /app/staticfiles /app/logs /app/static /app/media \
 && chown -R appuser:appuser /app

# Copy only application files needed at runtime.
COPY ./dealdata_common/*.py ./dealdata_common/
COPY ./gps_layer/manage.py ./manage.py
COPY ./gps_layer/__init__.py ./__init__.py
COPY ./gps_layer/gps/*.py ./gps/
COPY ./gps_layer/gps_data/*.py ./gps_data/
COPY ./gps_layer/gps_data/management/*.py ./gps_data/management/
COPY ./gps_layer/gps_data/management/commands/*.py ./gps_data/management/commands/
COPY ./gps_layer/gps_data/migrations/*.py ./gps_data/migrations/
COPY ./gps_layer/entrypoint.sh /entrypoint.sh

RUN chmod +x /entrypoint.sh \
    && chown appuser:appuser /entrypoint.sh \
    && find /app -name "*.pyc" -delete \
    && find /app -depth -type d -name "__pycache__" -exec rm -rf {} + \
    && find /app -depth -name "*.git*" -exec rm -rf {} +

USER 10001:10001

# Expose the port (optional but handy)
EXPOSE 7001

ENTRYPOINT ["/entrypoint.sh"]

# Startup command: Django ASGI via granian
CMD ["granian", "gps.asgi:application", "--interface", "asgi", "--host", "0.0.0.0", "--port", "7001", "--workers", "2"]
