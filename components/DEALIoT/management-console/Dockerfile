# syntax=docker/dockerfile:1.7

FROM python:3.13-alpine@sha256:399babc8b49529dabfd9c922f2b5eea81d611e4512e3ed250d75bd2e7683f4b0

WORKDIR /app

RUN addgroup -S -g 10001 appuser \
    && adduser -S -D -H -u 10001 -G appuser appuser

COPY --chown=root:root --chmod=0555 management-console/management_console /app/management_console
COPY --chown=root:root --chmod=0555 management-console/static /app/static

USER 10001:10001
ENV PYTHONDONTWRITEBYTECODE="1" \
    PYTHONPATH="/app" \
    MANAGEMENT_CONSOLE_BIND="0.0.0.0" \
    MANAGEMENT_CONSOLE_ALLOW_WILDCARD_BIND="true" \
    MANAGEMENT_CONSOLE_PORT="8080"

EXPOSE 8080
CMD ["python", "-m", "management_console.app"]
