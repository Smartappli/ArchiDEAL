# Pinned Alpine base: no HIGH/CRITICAL OS findings at build time.
FROM python:3.14-alpine@sha256:26730869004e2b9c4b9ad09cab8625e81d256d1ce97e72df5520e806b1709f92

ARG APP_HOME=/app
WORKDIR ${APP_HOME}

# Do not create .pyc files, unbuffered logs
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Copy and install Python dependencies
COPY ./core_layer/requirements.lock ./
RUN apk add --no-cache lz4-libs \
    && apk add --no-cache --virtual .lz4-build-deps build-base linux-headers lz4-dev \
    && pip install --no-cache-dir --require-hashes --only-binary :all: --no-binary lz4 -r requirements.lock \
    && apk del .lz4-build-deps

# Copy only application files needed at runtime.
COPY ./dealdata_common/*.py ./dealdata_common/
COPY ./core_layer/manage.py ./manage.py
COPY ./core_layer/auth/*.py ./auth/
COPY ./core_layer/auth/forgot_password/*.py ./auth/forgot_password/
COPY ./core_layer/auth/login/*.py ./auth/login/
COPY ./core_layer/auth/migrations/*.py ./auth/migrations/
COPY ./core_layer/auth/register/*.py ./auth/register/
COPY ./core_layer/auth/reset_password/*.py ./auth/reset_password/
COPY ./core_layer/auth/verify_email/*.py ./auth/verify_email/
COPY ./core_layer/core/*.py ./core/
COPY ./core_layer/core/template_helpers/*.py ./core/template_helpers/
COPY ./core_layer/core_data/*.py ./core_data/
COPY ./core_layer/core_data/migrations/*.py ./core_data/migrations/
COPY ./core_layer/entrypoint.sh /entrypoint.sh

RUN chmod +x /entrypoint.sh \
    && addgroup -S -g 10001 appuser \
    && adduser -S -D -H -u 10001 -G appuser appuser \
    && chown -R appuser:appuser /app /entrypoint.sh

USER 10001:10001

# Expose the port
EXPOSE 7000

ENTRYPOINT ["/entrypoint.sh"]

# Startup command: Django ASGI via granian
CMD ["granian", "core.asgi:application", "--interface", "asgi", "--host", "0.0.0.0", "--port", "7000", "--workers", "4"]
