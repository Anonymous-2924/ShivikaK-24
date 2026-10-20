# Phase 1 Makefile. Every target either works or prints a clear
# "not implemented in Phase 1" message. No silent no-ops.

PY := python
VENV := .venv
PIP := $(VENV)/bin/pip
PYTHON := $(VENV)/bin/python

.PHONY: help setup services services-down services-logs \
        generate-data ingest build-graph eval dev test lint clean

help:
	@echo "Targets:"
	@echo "  setup           Create venv, install deps (app + dev + datagen extras)"
	@echo "  services        Start Qdrant + Neo4j via docker compose"
	@echo "  services-down   Stop services (volumes preserved)"
	@echo "  services-logs   Tail service logs"
	@echo "  generate-data   Run standalone generator -> generated_data/   [Phase 2]"
	@echo "  ingest          Ingest files from data/inbox/                 [Phase 3]"
	@echo "  build-graph     Build Neo4j graph + Qdrant index              [Phase 4]"
	@echo "  eval            Run eval harness vs vector-RAG baseline       [Phase 6]"
	@echo "  dev             Launch API + UI dev server                    [Phase 7-8]"
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
	@echo "  3. source $(VENV)/bin/activate"

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

build-graph:
	$(PYTHON) -m cli build-graph

eval:
	$(PYTHON) -m eval.run

dev:
	@echo "Phase 7-8 target. Not implemented in Phase 1."
	@exit 1

test:
	$(PYTHON) -m pytest

lint:
	$(VENV)/bin/ruff check .

clean:
	rm -rf $(VENV) .pytest_cache .ruff_cache **/__pycache__ \
	       generated_data data/processed data/graph
