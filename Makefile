PYTHON ?= python
CSV ?= data/fuel-prices-for-be-assessment.csv

.PHONY: install migrate import run test coverage lint format bench

install:
	$(PYTHON) -m pip install -r requirements-dev.txt

migrate:
	$(PYTHON) manage.py migrate

import:
	$(PYTHON) manage.py import_stations $(CSV)

run:
	$(PYTHON) manage.py runserver

test:
	$(PYTHON) -m pytest

coverage:
	$(PYTHON) -m pytest --cov=apps --cov-report=term-missing

lint:
	$(PYTHON) -m ruff check .
	$(PYTHON) -m ruff format --check .

format:
	$(PYTHON) -m ruff check --fix .
	$(PYTHON) -m ruff format .

bench:
	$(PYTHON) scripts/benchmark.py
