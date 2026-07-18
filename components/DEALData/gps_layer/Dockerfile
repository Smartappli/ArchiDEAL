# Stage 1: Build with all dependencies
FROM python:3.14-alpine@sha256:26730869004e2b9c4b9ad09cab8625e81d256d1ce97e72df5520e806b1709f92 AS builder

ARG APP_HOME=/app
WORKDIR ${APP_HOME}

# Do not create .pyc files, unbuffered logs
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Copy and install Python dependencies
COPY ./gps_layer/requirements.lock ./
RUN apk add --no-cache --virtual .lz4-build-deps build-base linux-headers lz4-dev \
 && pip install --prefix=/install --no-cache-dir --require-hashes --only-binary :all: --no-binary lz4 -r requirements.lock \
 && find /install -name "*.pyc" -delete \
 && find /install -depth -type d -name "__pycache__" -exec rm -rf {} + \
 && apk del .lz4-build-deps

# Stage 2: Lightweight runtime image
FROM python:3.14-alpine@sha256:26730869004e2b9c4b9ad09cab8625e81d256d1ce97e72df5520e806b1709f92 AS runtime

ARG APP_HOME=/app
WORKDIR ${APP_HOME}

RUN apk add --no-cache lz4-libs

COPY --from=builder /install /usr/local

RUN addgroup -S -g 10001 appuser \
 && adduser -S -D -H -u 10001 -G appuser appuser \
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
