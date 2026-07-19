# syntax=docker/dockerfile:1.7

FROM python:3.14-alpine@sha256:26730869004e2b9c4b9ad09cab8625e81d256d1ce97e72df5520e806b1709f92

WORKDIR /app

COPY --chown=root:root --chmod=0444 management-console/requirements.lock /app/requirements.lock
RUN pip install --no-cache-dir --require-hashes --only-binary=:all: -r /app/requirements.lock

RUN addgroup -S -g 10001 appuser \
    && adduser -S -D -H -u 10001 -G appuser appuser

COPY --chown=root:root --chmod=0555 management-console/management_console /app/management_console
COPY --chown=root:root --chmod=0555 management-console/static /app/static

USER 10001:10001
ENV PYTHONDONTWRITEBYTECODE="1" \
    PYTHONUNBUFFERED="1" \
    PYTHONPATH="/app" \
    MANAGEMENT_CONSOLE_BIND="0.0.0.0" \
    MANAGEMENT_CONSOLE_ALLOW_WILDCARD_BIND="true" \
    MANAGEMENT_CONSOLE_PORT="8080"

EXPOSE 8080
CMD ["python", "-m", "management_console.app"]
