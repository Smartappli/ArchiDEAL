SHELL := /bin/sh

.PHONY: bootstrap config validate up smoke logs ps down test-interface test-host test-iot

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
