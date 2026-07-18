SHELL := /bin/sh

PRODUCTION_VALUES ?= deploy/kubernetes/values.example.yaml
PRODUCTION_OUTPUT ?= build/production
KUBE_CONTEXT ?=
APPROVE_LIVE_UPGRADE ?= 0
PRODUCTION_RELEASE_MANIFEST ?=
PRODUCTION_RELEASE_BUNDLE ?=
PRODUCTION_RELEASE_EVIDENCE_DIR ?=
PRODUCTION_SMOKE_TIMEOUT ?= 5m
ROLLBACK_VALUES ?=
ROLLBACK_RELEASE_MANIFEST ?=
ROLLBACK_RELEASE_BUNDLE ?=
ROLLBACK_RELEASE_EVIDENCE_DIR ?=
ROLLBACK_TIMEOUT ?= 15m
APPROVE_SCHEMA_COMPATIBLE_ROLLBACK ?= 0

.PHONY: bootstrap config validate up smoke logs ps down test-interface test-host test-iot production-example-validate production-render production-verify production-deploy production-smoke production-rollback

bootstrap:
	./scripts/bootstrap-env.sh

config:
	test -f .env || (echo "Run 'make bootstrap' first." >&2; exit 1)
	docker compose --env-file .env config --quiet

validate:
	python scripts/validate-monorepo.py

up: config
	docker compose --env-file .env up -d --build

smoke:
	./scripts/smoke-architecture.sh

logs:
	docker compose logs --follow --timestamps

ps:
	docker compose ps --all

down:
	docker compose down --remove-orphans

test-interface:
	cd components/DEALInterface && npm ci && npm run typecheck && npm run test:unit && npm run test:integration && npm run build

test-host:
	cd components/DEALHost && DJANGO_SETTINGS_MODULE=dealhost.settings.test python manage.py test tests --verbosity 2

test-iot:
	cd components/DEALIoT && python -m unittest discover -s tests/unit -p 'test_*.py' -v

production-example-validate:
	python deploy/kubernetes/render.py --allow-example --force --values deploy/kubernetes/values.example.yaml --output build/production-example

production-render:
	python deploy/kubernetes/render.py --force --values $(PRODUCTION_VALUES) --output $(PRODUCTION_OUTPUT)

production-verify:
	test -n "$(PRODUCTION_RELEASE_MANIFEST)" || (echo "Set PRODUCTION_RELEASE_MANIFEST." >&2; exit 1)
	test -n "$(PRODUCTION_RELEASE_BUNDLE)" || (echo "Set PRODUCTION_RELEASE_BUNDLE." >&2; exit 1)
	test -n "$(PRODUCTION_RELEASE_EVIDENCE_DIR)" || (echo "Set PRODUCTION_RELEASE_EVIDENCE_DIR." >&2; exit 1)
	python deploy/kubernetes/verify-release.py \
		--values "$(PRODUCTION_VALUES)" \
		--manifest "$(PRODUCTION_RELEASE_MANIFEST)" \
		--bundle "$(PRODUCTION_RELEASE_BUNDLE)" \
		--evidence-dir "$(PRODUCTION_RELEASE_EVIDENCE_DIR)"

production-deploy:
	test -n "$(KUBE_CONTEXT)" || (echo "Set KUBE_CONTEXT." >&2; exit 1)
	test -n "$(ARCHIDEAL_BEARER_TOKEN_FILE)" || (echo "Set ARCHIDEAL_BEARER_TOKEN_FILE." >&2; exit 1)
	test -n "$(PRODUCTION_RELEASE_MANIFEST)" || (echo "Set PRODUCTION_RELEASE_MANIFEST." >&2; exit 1)
	test -n "$(PRODUCTION_RELEASE_BUNDLE)" || (echo "Set PRODUCTION_RELEASE_BUNDLE." >&2; exit 1)
	test -n "$(PRODUCTION_RELEASE_EVIDENCE_DIR)" || (echo "Set PRODUCTION_RELEASE_EVIDENCE_DIR." >&2; exit 1)
	deploy/kubernetes/deploy-production.sh \
		--values "$(PRODUCTION_VALUES)" \
		--context "$(KUBE_CONTEXT)" \
		--smoke-token-file "$(ARCHIDEAL_BEARER_TOKEN_FILE)" \
		--release-manifest "$(PRODUCTION_RELEASE_MANIFEST)" \
		--release-bundle "$(PRODUCTION_RELEASE_BUNDLE)" \
		--release-evidence-dir "$(PRODUCTION_RELEASE_EVIDENCE_DIR)" \
		$(if $(filter 1 true yes,$(APPROVE_LIVE_UPGRADE)),--approve-live-upgrade,)

production-smoke:
	test -n "$(KUBE_CONTEXT)" || (echo "Set KUBE_CONTEXT." >&2; exit 1)
	test -n "$(ARCHIDEAL_BEARER_TOKEN_FILE)" || (echo "Set ARCHIDEAL_BEARER_TOKEN_FILE." >&2; exit 1)
	test -n "$(ARCHIDEAL_INGEST_TOKEN_FILE)" || (echo "Set ARCHIDEAL_INGEST_TOKEN_FILE." >&2; exit 1)
	deploy/kubernetes/smoke-production.sh \
		--values "$(PRODUCTION_VALUES)" \
		--context "$(KUBE_CONTEXT)" \
		--smoke-token-file "$(ARCHIDEAL_BEARER_TOKEN_FILE)" \
		--ingest-token-file "$(ARCHIDEAL_INGEST_TOKEN_FILE)" \
		--timeout "$(PRODUCTION_SMOKE_TIMEOUT)"

production-rollback:
	test -n "$(KUBE_CONTEXT)" || (echo "Set KUBE_CONTEXT." >&2; exit 1)
	test -n "$(ARCHIDEAL_BEARER_TOKEN_FILE)" || (echo "Set ARCHIDEAL_BEARER_TOKEN_FILE." >&2; exit 1)
	test -n "$(ROLLBACK_VALUES)" || (echo "Set ROLLBACK_VALUES to the previous release values." >&2; exit 1)
	test -n "$(ROLLBACK_RELEASE_MANIFEST)" || (echo "Set ROLLBACK_RELEASE_MANIFEST." >&2; exit 1)
	test -n "$(ROLLBACK_RELEASE_BUNDLE)" || (echo "Set ROLLBACK_RELEASE_BUNDLE." >&2; exit 1)
	test -n "$(ROLLBACK_RELEASE_EVIDENCE_DIR)" || (echo "Set ROLLBACK_RELEASE_EVIDENCE_DIR." >&2; exit 1)
	test "$(APPROVE_SCHEMA_COMPATIBLE_ROLLBACK)" = "1" || (echo "Set APPROVE_SCHEMA_COMPATIBLE_ROLLBACK=1 after expand/contract review." >&2; exit 1)
	deploy/kubernetes/rollback-production.sh \
		--values "$(ROLLBACK_VALUES)" \
		--context "$(KUBE_CONTEXT)" \
		--smoke-token-file "$(ARCHIDEAL_BEARER_TOKEN_FILE)" \
		--release-manifest "$(ROLLBACK_RELEASE_MANIFEST)" \
		--release-bundle "$(ROLLBACK_RELEASE_BUNDLE)" \
		--release-evidence-dir "$(ROLLBACK_RELEASE_EVIDENCE_DIR)" \
		--timeout "$(ROLLBACK_TIMEOUT)" \
		--approve-schema-compatible
