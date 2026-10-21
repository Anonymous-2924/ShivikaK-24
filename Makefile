# All targets run from the project root. If `make <target>` says `python:
# command not found` or similar, `make setup` first to create .venv.

PY := python3
VENV := .venv
PIP := $(VENV)/bin/pip
PYTHON := $(VENV)/bin/python

.PHONY: help setup services services-down services-logs \
        generate-data ingest extract resolve review-merges unmerge \
        build-graph query eval api dev test lint clean

help:
	@echo "Targets:"
	@echo "  setup           Create venv, install deps (app + dev + datagen extras)"
	@echo "  services        Start Qdrant + Neo4j via docker compose"
	@echo "  services-down   Stop services (volumes preserved)"
	@echo "  services-logs   Tail service logs"
	@echo "  generate-data   Run standalone generator -> generated_data/"
	@echo "  ingest          Ingest files from data/inbox/              [Phase 3]"
	@echo "  extract         LLM entity + relation extraction            [Phase 4]"
	@echo "  review-merges   Interactive ER review queue                 [Phase 4]"
	@echo "  unmerge         Reverse a merge: make unmerge ENTITY=<id>   [Phase 4]"
	@echo "  build-graph     Build Neo4j graph from all sources          [Phase 4]"
	@echo "  query           Ask the hybrid retrieval router a question  [Phase 5]"
	@echo "                  usage: make query QUESTION=\"...\" [AS_OF=YYYY-MM-DD]"
	@echo "  eval            Run eval harness vs vector-RAG baseline     [Phase 6]"
	@echo "  api             Run the FastAPI server                     [Phase 7]"
	@echo "  dev             Launch API + UI dev server                  [Phase 7-8]"
	@echo "  test            Run pytest"
	@echo "  lint            Run ruff"
	@echo "  clean           Remove venv, caches, generated artifacts"

$(VENV)/bin/activate:
	$(PY) -m venv $(VENV)
	$(PIP) install --upgrade pip wheel

setup: $(VENV)/bin/activate
	$(PIP) install -e ".[dev,datagen]"
	@echo ""
	@echo "Setup complete. Next:"
	@echo "  1. cp .env.example .env  && edit it"
	@echo "  2. make services"
	@echo "  3. source $(VENV)/bin/activate   (optional — Make targets use .venv directly)"

services:
	docker compose up -d
	@echo "Qdrant:  http://localhost:6333/dashboard"
	@echo "Neo4j:   http://localhost:7474  (user: neo4j, pass: see .env)"

services-down:
	docker compose down

services-logs:
	docker compose logs -f --tail=100

generate-data:
	$(PYTHON) -m tools.datagen.generate --suppliers 500 --skus 2000 --seed 42

ingest:
	$(PYTHON) -m cli ingest

extract:
	$(PYTHON) -m cli extract

resolve:
	$(PYTHON) -m cli resolve

review-merges:
	$(PYTHON) -m cli review-merges

unmerge:
	@if [ -z "$(ENTITY)" ]; then \
		echo "usage: make unmerge ENTITY=<entity_id>"; exit 2; \
	fi
	$(PYTHON) -m cli unmerge $(ENTITY)

build-graph:
	$(PYTHON) -m cli build-graph

query:
	@if [ -z "$(QUESTION)" ]; then \
		echo "usage: make query QUESTION=\"...\" [AS_OF=YYYY-MM-DD]"; exit 2; \
	fi
	$(PYTHON) -m cli query "$(QUESTION)" $(if $(AS_OF),--as-of $(AS_OF),)

eval:
	$(PYTHON) -m eval.run

api:
	$(PYTHON) -m cli api

dev:
	@echo "Phase 8 target. Not yet implemented."
	@exit 1

test:
	$(PYTHON) -m pytest

lint:
	$(VENV)/bin/ruff check .

clean:
	rm -rf $(VENV) .pytest_cache .ruff_cache **/__pycache__ \
	       generated_data data/processed data/graph
