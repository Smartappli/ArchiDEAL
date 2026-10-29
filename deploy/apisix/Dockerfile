FROM python:3.14-alpine@sha256:601e99e090cb08c2784a42395487709500bc39930307fe72f3f11a8f3c430762

RUN addgroup -S -g 10001 archideal \
    && adduser -S -D -H -u 10001 -G archideal archideal

WORKDIR /bootstrap
COPY --chown=10001:10001 --chmod=0555 \
    bootstrap.py health.py private_network_preflight.py /bootstrap/

USER 10001:10001

ENTRYPOINT ["python", "/bootstrap/bootstrap.py"]
