# syntax=docker/dockerfile:1.7

FROM python:3.13-slim@sha256:6771159cd4fa5d9bba1258caf0b82e6b73458c694d178ad97c5e925c2d0e1a91

WORKDIR /app

RUN groupadd --gid 10001 appuser \
    && useradd --uid 10001 --gid appuser --create-home --shell /usr/sbin/nologin appuser

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
