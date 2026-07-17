# Base Python slim image
FROM python:3.14-slim

ARG APP_HOME=/app
WORKDIR ${APP_HOME}

# Do not create .pyc files, unbuffered logs
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Install system dependencies
# hadolint ignore=DL3008
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
  && rm -rf /var/lib/apt/lists/*

# Copy and install Python dependencies
COPY ./core_layer/requirements.lock ./
RUN pip install --no-cache-dir --require-hashes --only-binary :all: -r requirements.lock

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
    && useradd -m appuser \
    && chown -R appuser:appuser /app /entrypoint.sh

USER appuser

# Expose the port
EXPOSE 7000

ENTRYPOINT ["/entrypoint.sh"]

# Startup command: Django ASGI via granian
CMD ["granian", "core.asgi:application", "--interface", "asgi", "--host", "0.0.0.0", "--port", "7000", "--workers", "4"]
