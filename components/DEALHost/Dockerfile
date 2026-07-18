FROM python:3.14-slim@sha256:d3400aa122fa42cf0af0dbe8ec3091b047eac5c8f7e3539f7135e86d855dc015

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DEALHOST_DB_PATH=/data/db.sqlite3

WORKDIR /app

RUN groupadd --system --gid 10001 dealhost \
    && useradd --system --uid 10001 --gid dealhost \
        --home-dir /app --shell /usr/sbin/nologin dealhost

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
