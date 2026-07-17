# syntax=docker/dockerfile:1.7

FROM python:3.13-slim

WORKDIR /app

RUN useradd --create-home --shell /bin/bash appuser

COPY --chown=root:root --chmod=0555 management-console/management_console /app/management_console
COPY --chown=root:root --chmod=0555 management-console/static /app/static

USER appuser
ENV PYTHONDONTWRITEBYTECODE="1" \
    PYTHONPATH="/app" \
    MANAGEMENT_CONSOLE_BIND="0.0.0.0" \
    MANAGEMENT_CONSOLE_ALLOW_WILDCARD_BIND="true" \
    MANAGEMENT_CONSOLE_PORT="8080"

EXPOSE 8080
CMD ["python", "-m", "management_console.app"]
