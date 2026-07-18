FROM python:3.14-alpine@sha256:26730869004e2b9c4b9ad09cab8625e81d256d1ce97e72df5520e806b1709f92

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DEALHOST_DB_PATH=/data/db.sqlite3

WORKDIR /app

RUN addgroup -S -g 10001 dealhost \
    && adduser -S -D -H -u 10001 -G dealhost dealhost

COPY requirements.lock /tmp/requirements.lock

RUN pip install --no-cache-dir --require-hashes --only-binary :all: \
        -r /tmp/requirements.lock \
    && rm /tmp/requirements.lock

COPY --chown=10001:10001 . /app

RUN mkdir -p /data /app/staticfiles \
    && chown -R 10001:10001 /data /app/staticfiles

USER 10001:10001

EXPOSE 8000

ENTRYPOINT ["/app/docker-entrypoint.sh"]
CMD ["granian", "--host", "0.0.0.0", "--port", "8000", "--interface", "asgi", "dealhost.asgi:application"]
