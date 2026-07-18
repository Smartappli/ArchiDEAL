FROM python:3.14-alpine@sha256:26730869004e2b9c4b9ad09cab8625e81d256d1ce97e72df5520e806b1709f92

RUN addgroup -S -g 10001 archideal \
    && adduser -S -D -H -u 10001 -G archideal archideal

WORKDIR /bootstrap
COPY --chown=10001:10001 --chmod=0555 \
    bootstrap.py health.py private_network_preflight.py /bootstrap/

USER 10001:10001

ENTRYPOINT ["python", "/bootstrap/bootstrap.py"]
