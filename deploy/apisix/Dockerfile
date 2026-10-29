FROM python:3.14-alpine@sha256:eb2c62658b8d51bff0acc408504b76521d02030de56a8a3c1e830083e89b89d2

RUN addgroup -S -g 10001 archideal \
    && adduser -S -D -H -u 10001 -G archideal archideal

WORKDIR /bootstrap
COPY --chown=10001:10001 --chmod=0555 \
    bootstrap.py health.py private_network_preflight.py /bootstrap/

USER 10001:10001

ENTRYPOINT ["python", "/bootstrap/bootstrap.py"]
