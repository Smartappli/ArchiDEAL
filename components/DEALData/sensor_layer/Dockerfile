# Pinned Alpine base: no HIGH/CRITICAL OS findings at build time.
FROM python:3.14-alpine@sha256:26730869004e2b9c4b9ad09cab8625e81d256d1ce97e72df5520e806b1709f92

ARG APP_HOME=/app
WORKDIR ${APP_HOME}

# Do not create .pyc files, unbuffered logs
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Copy and install Python dependencies
COPY ./sensor_layer/requirements.lock ./
RUN pip install --no-cache-dir --require-hashes --only-binary :all: -r requirements.lock

# Copy only application files needed at runtime.
COPY ./dealdata_common/*.py ./dealdata_common/
COPY ./sensor_layer/manage.py ./manage.py
COPY ./sensor_layer/sensor/*.py ./sensor/
COPY ./sensor_layer/sensor_data/*.py ./sensor_data/
COPY ./sensor_layer/sensor_data/management/*.py ./sensor_data/management/
COPY ./sensor_layer/sensor_data/management/commands/*.py ./sensor_data/management/commands/
COPY ./sensor_layer/sensor_data/migrations/*.py ./sensor_data/migrations/
COPY ./sensor_layer/entrypoint.sh /entrypoint.sh

# User non-root
RUN chmod +x /entrypoint.sh \
    && addgroup -S -g 10001 appuser \
    && adduser -S -D -H -u 10001 -G appuser appuser \
    && chown -R appuser:appuser /app /entrypoint.sh
USER 10001:10001

# Expose the port
EXPOSE 7002

ENTRYPOINT ["/entrypoint.sh"]

# Startup command: Django ASGI via granian
CMD ["granian", "sensor.asgi:application", "--interface", "asgi", "--host", "0.0.0.0", "--port", "7002", "--workers", "4"]
