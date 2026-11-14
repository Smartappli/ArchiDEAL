FROM python:3.14-alpine@sha256:5862d971d1f0ae26b258cefa4e893556b1d3aba81bd2ff30888704ad378bab67

RUN addgroup -S -g 10001 archideal \
    && adduser -S -D -H -u 10001 -G archideal archideal

WORKDIR /bootstrap
COPY --chown=10001:10001 --chmod=0555 \
    bootstrap.py health.py private_network_preflight.py /bootstrap/

USER 10001:10001

ENTRYPOINT ["python", "/bootstrap/bootstrap.py"]
