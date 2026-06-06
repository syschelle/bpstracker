SHELL := /bin/bash
COMPOSE := docker compose
APP_DIR := /opt/bpstracker

.PHONY: init up up-detached down restart logs ps test backend-shell frontend-shell reset-db prepare-opt install-opt deploy-opt backup-db check-exposure

init:
	@bash -lc 'source scripts/env-setup.sh; profile="$${BPSTRACKER_INSTALL_PROFILE:-regular}"; bpstracker_prepare_env .env "$$profile" v0.9.9'
	@mkdir -p data/postgres data/backend backups

up: init
	$(COMPOSE) build --progress=plain
	$(COMPOSE) up

up-detached: init
	$(COMPOSE) build --progress=plain
	$(COMPOSE) up -d

restart:
	$(COMPOSE) restart

down:
	$(COMPOSE) down

logs:
	$(COMPOSE) logs -f --tail=200

ps:
	$(COMPOSE) ps

test:
	$(COMPOSE) run --rm backend pytest -q

backend-shell:
	$(COMPOSE) exec backend /bin/sh

frontend-shell:
	$(COMPOSE) exec frontend /bin/sh

reset-db:
	$(COMPOSE) down
	@rm -rf data/postgres
	@mkdir -p data/postgres

prepare-opt:
	sudo mkdir -p $(APP_DIR)
	sudo chown -R $$USER:$$USER $(APP_DIR)
	mkdir -p $(APP_DIR)/data/postgres $(APP_DIR)/data/backend $(APP_DIR)/backups

install-opt:
	./scripts/deploy-opt.sh

deploy-opt:
	./scripts/deploy-opt.sh

backup-db:
	@mkdir -p backups
	$(COMPOSE) exec -T postgres pg_dump -U $${POSTGRES_USER:-bpstracker} $${POSTGRES_DB:-bpstracker} > backups/bpstracker-$$(date +%Y%m%d-%H%M%S).sql

check-exposure:
	./scripts/check-exposure.sh
